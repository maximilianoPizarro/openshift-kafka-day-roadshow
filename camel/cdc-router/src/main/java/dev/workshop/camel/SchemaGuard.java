package dev.workshop.camel;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Named;
import org.apache.camel.Exchange;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@ApplicationScoped
@Named("schemaGuard")
public class SchemaGuard {
    public static final String SCHEMA = "schemaArtifact";
    public static final String SOURCE = "eventSource";
    public static final String ORIGINAL = "originalBody";

    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private final JsonSchemaFactory schemas = JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012);
    private final ConcurrentHashMap<String, Cached> cache = new ConcurrentHashMap<>();

    @SuppressWarnings("unchecked")
    public Map<String, Object> customerAfter(Map<String, Object> body) {
        return after(body);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> orderAfter(Map<String, Object> body) {
        return after(body);
    }

    public void validateCustomer(Map<String, Object> row) {
        validate("customers-value", row);
    }

    public void validateOrder(Map<String, Object> row) {
        validate("orders-value", row);
    }

    public String successBody(Exchange exchange) throws Exception {
        ObjectNode node = mapper.createObjectNode();
        node.put("schema", exchange.getProperty(SCHEMA, String.class));
        node.put("source", exchange.getProperty(SOURCE, String.class));
        node.set("after", mapper.valueToTree(exchange.getMessage().getBody()));
        return mapper.writeValueAsString(node);
    }

    public String errorBody(Exchange exchange) throws Exception {
        Exception caught = exchange.getProperty(Exchange.EXCEPTION_CAUGHT, Exception.class);
        String message = caught == null || caught.getMessage() == null
                ? "validation failed"
                : caught.getMessage();
        ObjectNode node = mapper.createObjectNode();
        node.put("error", message);
        node.put("source", exchange.getProperty(SOURCE, "unknown", String.class));
        node.put("payload", exchange.getProperty(ORIGINAL, "", String.class));
        return mapper.writeValueAsString(node);
    }

    /**
     * Fetch failures are {@link IllegalStateException} and must leave the route
     * so Camel redelivers. Validation and parse errors stay handled.
     */
    public void rethrowIfFetchFailure(Exchange exchange) {
        Exception caught = exchange.getProperty(Exchange.EXCEPTION_CAUGHT, Exception.class);
        if (hasCause(caught, IllegalStateException.class) && !hasCause(caught, SchemaValidationException.class)) {
            if (caught instanceof RuntimeException runtime) {
                throw runtime;
            }
            throw new IllegalStateException(caught);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> after(Map<String, Object> body) {
        if (body == null) {
            throw new SchemaValidationException("missing after");
        }
        Map<String, Object> envelope = body;
        Object payload = body.get("payload");
        if (payload instanceof Map<?, ?> payloadMap && payloadMap.containsKey("after")) {
            envelope = (Map<String, Object>) payloadMap;
        }
        Object after = envelope.get("after");
        if (!(after instanceof Map<?, ?>)) {
            throw new SchemaValidationException("missing after");
        }
        return (Map<String, Object>) after;
    }

    private void validate(String artifact, Map<String, Object> row) {
        Set<ValidationMessage> errors = schema(artifact).validate(mapper.valueToTree(row));
        if (!errors.isEmpty()) {
            throw new SchemaValidationException(errors.iterator().next().getMessage());
        }
    }

    private JsonSchema schema(String artifact) {
        Cached cached = cache.get(artifact);
        if (cached != null && cached.expires.isAfter(Instant.now())) {
            return cached.schema;
        }
        String url = baseUrl() + "/apis/registry/v3/groups/workshop/artifacts/" + artifact + "/versions/1/content";
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                throw new IllegalStateException("schema fetch " + artifact + " HTTP " + response.statusCode());
            }
            JsonNode tree = mapper.readTree(response.body());
            JsonSchema parsed = schemas.getSchema(tree);
            cache.put(artifact, new Cached(parsed, Instant.now().plusSeconds(30)));
            return parsed;
        } catch (IllegalStateException e) {
            throw e;
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("schema fetch " + artifact + " failed: " + e.getMessage(), e);
        }
    }

    private String baseUrl() {
        String value = System.getenv().getOrDefault(
                "APICURIO_BASE_URL",
                "http://cdc-registry-app-service.kafka-cdc.svc:8080");
        if (value.endsWith("/")) {
            return value.substring(0, value.length() - 1);
        }
        return value;
    }

    private boolean hasCause(Throwable error, Class<? extends Throwable> type) {
        Throwable current = error;
        while (current != null) {
            if (type.isInstance(current)) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private record Cached(JsonSchema schema, Instant expires) {
    }
}

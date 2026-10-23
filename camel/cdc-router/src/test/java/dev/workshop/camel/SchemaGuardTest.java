package dev.workshop.camel;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class SchemaGuardTest {
    private final SchemaGuard guard = new SchemaGuard();

    @Test
    void readsAfterFromDebeziumPayload() {
        Map<String, Object> row = Map.of("email", "a@b.co");
        Map<String, Object> payload = new HashMap<>();
        payload.put("before", null);
        payload.put("after", row);
        Map<String, Object> body = Map.of("schema", Map.of(), "payload", payload);

        assertSame(row, guard.customerAfter(body));
    }

    @Test
    void readsTopLevelAfter() {
        Map<String, Object> row = Map.of("product", "loan");
        Map<String, Object> body = new HashMap<>();
        body.put("after", row);

        assertSame(row, guard.orderAfter(body));
    }

    @Test
    void rejectsMissingAfter() {
        Map<String, Object> payload = new HashMap<>();
        payload.put("after", null);
        Map<String, Object> body = Map.of("payload", payload);

        assertThrows(SchemaValidationException.class, () -> guard.customerAfter(body));
    }
}

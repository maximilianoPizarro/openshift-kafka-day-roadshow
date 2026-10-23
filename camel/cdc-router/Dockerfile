FROM registry.access.redhat.com/ubi9/openjdk-21:latest AS build
USER 0
WORKDIR /work
COPY . .
RUN chown -R 185:0 /work && chmod -R g+w /work
USER 185
ENV MAVEN_OPTS="-Xmx1024m"
RUN mvn -B -DskipTests package

FROM registry.access.redhat.com/ubi9/openjdk-21-runtime:latest
COPY --from=build --chown=185:0 /work/target/quarkus-app/ /deployments/
WORKDIR /deployments
USER 185
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "quarkus-run.jar"]

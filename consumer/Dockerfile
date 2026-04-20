# Multi-stage build keeps the runtime image small (~170 MB).
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src

# Cache dependencies first to speed up rebuilds.
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -q clean package -DskipTests

# ------------------------------------------------------------------
FROM eclipse-temurin:17-jre-alpine

RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=build /src/target/consumer.jar /app/consumer.jar
RUN chown -R app:app /app
USER app

EXPOSE 8080

# JVM tuning suitable for a small container (~256 MiB limit).
ENV JAVA_OPTS="-XX:+UseContainerSupport -XX:MaxRAMPercentage=75"

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s \
  CMD wget -q -O- http://127.0.0.1:8080/actuator/health || exit 1

ENTRYPOINT ["sh","-c","exec java $JAVA_OPTS -jar /app/consumer.jar"]

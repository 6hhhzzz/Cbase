# KES Java Backend Dockerfile — 多阶段构建
# 阶段 1: Maven 编译
FROM maven:3.9-eclipse-temurin-17-alpine AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -B 2>/dev/null || true
COPY src ./src
RUN mvn package -DskipTests -B

# 阶段 2: 运行时
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -qO- http://localhost:8080/api/health 2>/dev/null || exit 1
ENTRYPOINT ["java", "-jar", "app.jar"]

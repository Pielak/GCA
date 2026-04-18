"""DT-058 Sprint 2.2 — Scaffolder Java/Quarkus.

Variante alternativa a Spring Boot. Quarkus é a escolha comum quando o
cliente prioriza:
- startup time (cold start <1s, ideal pra container/serverless)
- footprint de memória (RSS ~100MB vs ~300MB do Spring Boot tradicional)
- compatibilidade com GraalVM native image

Layout produzido:
    pom.xml
    .gitignore
    README.md
    src/main/java/<package>/GreetingResource.java   (resource simples)
    src/main/resources/application.properties
    src/test/java/<package>/GreetingResourceTest.java

Decisões:
- Quarkus 3.x (LTS) com Java 21.
- Maven (Quarkus suporta Maven e Gradle igualmente; Maven é mais comum
  em clientes enterprise BR).
- `application.properties` em vez de YAML — é o padrão do Quarkus,
  diferente de Spring Boot.
- Reactive disabilitado por default — adicionar `quarkus-rest-jackson`
  pra REST clássico.
- Postgres via `quarkus-jdbc-postgresql` + `quarkus-hibernate-orm-panache`.
"""
from typing import List

from .types import ScaffoldFile, ScaffoldSpec
from .java_spring import _class_name_from_slug, _package_to_path, _gitignore


_QUARKUS_DEFAULT_VERSION = "3.13.0"


def _pom_xml(spec: ScaffoldSpec) -> str:
    quarkus_version = spec.framework_version or _QUARKUS_DEFAULT_VERSION

    deps_extra: List[str] = []
    if spec.requires_security:
        deps_extra.append(
            "        <dependency>\n"
            "            <groupId>io.quarkus</groupId>\n"
            "            <artifactId>quarkus-security-jpa-reactive</artifactId>\n"
            "        </dependency>\n"
            "        <dependency>\n"
            "            <groupId>io.quarkus</groupId>\n"
            "            <artifactId>quarkus-smallrye-jwt</artifactId>\n"
            "        </dependency>"
        )
    if spec.requires_redis:
        deps_extra.append(
            "        <dependency>\n"
            "            <groupId>io.quarkus</groupId>\n"
            "            <artifactId>quarkus-redis-client</artifactId>\n"
            "        </dependency>"
        )
    if (spec.database or "").lower().startswith("postgres"):
        deps_extra.append(
            "        <dependency>\n"
            "            <groupId>io.quarkus</groupId>\n"
            "            <artifactId>quarkus-jdbc-postgresql</artifactId>\n"
            "        </dependency>\n"
            "        <dependency>\n"
            "            <groupId>io.quarkus</groupId>\n"
            "            <artifactId>quarkus-hibernate-orm-panache</artifactId>\n"
            "        </dependency>"
        )

    extra_str = "\n".join(deps_extra)
    extra_block = f"\n{extra_str}\n" if extra_str else "\n"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Auto-gerado pelo GCA — não editar manualmente.
     Projeto: {spec.project_name}
     Stack: Java {spec.java_version} / Quarkus {quarkus_version}
     [gca:auto] -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>{spec.package}</groupId>
    <artifactId>{spec.project_slug}</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <name>{spec.project_name}</name>

    <properties>
        <maven.compiler.release>{spec.java_version}</maven.compiler.release>
        <quarkus.platform.version>{quarkus_version}</quarkus.platform.version>
        <quarkus.platform.group-id>io.quarkus.platform</quarkus.platform.group-id>
        <quarkus.platform.artifact-id>quarkus-bom</quarkus.platform.artifact-id>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>${{quarkus.platform.group-id}}</groupId>
                <artifactId>${{quarkus.platform.artifact-id}}</artifactId>
                <version>${{quarkus.platform.version}}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-rest-jackson</artifactId>
        </dependency>
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-smallrye-health</artifactId>
        </dependency>
{extra_block}
        <dependency>
            <groupId>io.quarkus</groupId>
            <artifactId>quarkus-junit5</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.rest-assured</groupId>
            <artifactId>rest-assured</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>${{quarkus.platform.group-id}}</groupId>
                <artifactId>quarkus-maven-plugin</artifactId>
                <version>${{quarkus.platform.version}}</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>build</goal>
                            <goal>generate-code</goal>
                            <goal>generate-code-tests</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
"""


def _greeting_resource_java(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — endpoint exemplo. Substitua pela sua API. [gca:auto]
package {spec.package};

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/api/greeting")
public class GreetingResource {{

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public String greeting() {{
        return "{{\\"app\\": \\"{spec.project_slug}\\", \\"status\\": \\"ok\\"}}";
    }}
}}
"""


def _application_properties(spec: ScaffoldSpec) -> str:
    lines = [
        "# Auto-gerado pelo GCA — ajuste ENV e secrets via deploy. [gca:auto]",
        f"quarkus.application.name={spec.project_slug}",
        "quarkus.http.port=${PORT:8080}",
        "",
        "# Health checks (Smallrye Health expõe em /q/health automaticamente)",
        "quarkus.smallrye-health.root-path=/q/health",
        "",
        f"quarkus.log.level=INFO",
        f"quarkus.log.category.\"{spec.package}\".level=DEBUG",
    ]
    if (spec.database or "").lower().startswith("postgres"):
        lines.extend([
            "",
            "# Datasource Postgres",
            "quarkus.datasource.db-kind=postgresql",
            "quarkus.datasource.username=${DATABASE_USER:app}",
            "quarkus.datasource.password=${DATABASE_PASSWORD:changeme}",
            "quarkus.datasource.jdbc.url=${DATABASE_URL:jdbc:postgresql://localhost:5432/app}",
            "quarkus.hibernate-orm.database.generation=validate",
        ])
    if spec.requires_redis:
        lines.extend([
            "",
            "# Redis",
            "quarkus.redis.hosts=${REDIS_URL:redis://localhost:6379}",
        ])
    return "\n".join(lines) + "\n"


def _greeting_resource_test_java(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA — smoke test do endpoint. [gca:auto]
package {spec.package};

import io.quarkus.test.junit.QuarkusTest;
import org.junit.jupiter.api.Test;

import static io.restassured.RestAssured.given;
import static org.hamcrest.CoreMatchers.containsString;

@QuarkusTest
class GreetingResourceTest {{

    @Test
    void testGreetingEndpoint() {{
        given()
            .when().get("/api/greeting")
            .then()
            .statusCode(200)
            .body(containsString("ok"));
    }}
}}
"""


def _readme(spec: ScaffoldSpec) -> str:
    return f"""# {spec.project_name}

> Scaffold inicial **Quarkus** gerado pelo GCA. Edite normalmente —
> apenas arquivos com cabeçalho `[gca:auto]` podem ser sobrescritos
> em regenerações futuras.

## Stack

- Java {spec.java_version}
- Quarkus {spec.framework_version or _QUARKUS_DEFAULT_VERSION}
- Maven
{f"- {spec.database}" if spec.database else ""}
{"- Redis" if spec.requires_redis else ""}
{"- SmallRye JWT (auth)" if spec.requires_security else ""}

## Como rodar (dev mode com live reload)

```bash
./mvnw quarkus:dev
# ou
mvn quarkus:dev
```

App em `http://localhost:8080`. Endpoint exemplo: `/api/greeting`.
Health checks: `/q/health` (live), `/q/health/ready` (ready).

## Build nativo (GraalVM)

```bash
./mvnw package -Pnative
# binário: target/{spec.project_slug}-runner
```

## Testes

```bash
./mvnw test
```
"""


def scaffold_java_quarkus(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial determinística de um projeto Quarkus.

    Mesma interface do `scaffold_java_spring` — caller pode despachar
    por `framework` no OCG.STACK_RECOMMENDATION.backend.framework.
    """
    pkg_path = _package_to_path(spec.package)
    files: List[ScaffoldFile] = [
        ScaffoldFile("pom.xml", _pom_xml(spec)),
        ScaffoldFile(".gitignore", _gitignore()),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile(
            f"src/main/java/{pkg_path}/GreetingResource.java",
            _greeting_resource_java(spec),
        ),
        ScaffoldFile(
            "src/main/resources/application.properties",
            _application_properties(spec),
        ),
        ScaffoldFile(
            f"src/test/java/{pkg_path}/GreetingResourceTest.java",
            _greeting_resource_test_java(spec),
        ),
    ]
    return files

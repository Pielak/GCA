"""DT-058 Sprint 3.4 — Scaffolder Kotlin / Spring Boot.

Gera estrutura inicial Spring Boot 3.x com Kotlin + Gradle Kotlin DSL.
Não chama LLM.

Layout produzido:
    build.gradle.kts
    settings.gradle.kts
    .gitignore
    README.md
    src/main/kotlin/<package>/Application.kt
    src/main/kotlin/<package>/config/SecurityConfig.kt   (se requires_security)
    src/main/resources/application.yml
    src/test/kotlin/<package>/ApplicationTests.kt

Decisões:
- Gradle Kotlin DSL (`build.gradle.kts`) — convenção Kotlin moderna,
  preferida sobre Maven em projetos Kotlin.
- Spring Boot 3.3 + Kotlin 2.0.
- Kotlin idiomático: arquivo `Application.kt` com `fun main` top-level
  + `@SpringBootApplication open class`.
- Reusa `_class_name_from_slug` e `_package_to_path` do java_spring.
"""
from typing import List

from .types import ScaffoldFile, ScaffoldSpec
from .java_spring import _class_name_from_slug, _package_to_path


_SPRING_BOOT_VERSION = "3.3.0"
_KOTLIN_VERSION = "2.0.0"


def _build_gradle_kts(spec: ScaffoldSpec) -> str:
    boot = spec.framework_version or _SPRING_BOOT_VERSION
    deps_extra = []
    if spec.requires_security:
        deps_extra.append('    implementation("org.springframework.boot:spring-boot-starter-security")')
    if spec.requires_redis:
        deps_extra.append('    implementation("org.springframework.boot:spring-boot-starter-data-redis")')
    if (spec.database or "").lower().startswith("postgres"):
        deps_extra.append('    implementation("org.springframework.boot:spring-boot-starter-data-jpa")')
        deps_extra.append('    runtimeOnly("org.postgresql:postgresql")')

    extra = ("\n" + "\n".join(deps_extra)) if deps_extra else ""

    return f"""// Auto-gerado pelo GCA — Gradle Kotlin DSL. [gca:auto]
plugins {{
    id("org.springframework.boot") version "{boot}"
    id("io.spring.dependency-management") version "1.1.5"
    kotlin("jvm") version "{_KOTLIN_VERSION}"
    kotlin("plugin.spring") version "{_KOTLIN_VERSION}"
}}

group = "{spec.package}"
version = "0.1.0-SNAPSHOT"

java {{
    sourceCompatibility = JavaVersion.VERSION_{spec.java_version}
}}

repositories {{
    mavenCentral()
}}

dependencies {{
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
    implementation("org.jetbrains.kotlin:kotlin-reflect"){extra}

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")
}}

tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {{
    kotlinOptions {{
        freeCompilerArgs = listOf("-Xjsr305=strict")
        jvmTarget = "{spec.java_version}"
    }}
}}

tasks.withType<Test> {{
    useJUnitPlatform()
}}
"""


def _settings_gradle_kts(spec: ScaffoldSpec) -> str:
    return f"""// Auto-gerado pelo GCA. [gca:auto]
rootProject.name = "{spec.project_slug}"
"""


def _application_kt(spec: ScaffoldSpec) -> str:
    cls = _class_name_from_slug(spec.project_slug) + "Application"
    return f"""// Auto-gerado pelo GCA — entrypoint Spring Boot Kotlin. [gca:auto]
package {spec.package}

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
open class {cls}

fun main(args: Array<String>) {{
    runApplication<{cls}>(*args)
}}
"""


def _application_yml(spec: ScaffoldSpec) -> str:
    db_block = ""
    if (spec.database or "").lower().startswith("postgres"):
        db_block = (
            "  datasource:\n"
            "    url: ${DATABASE_URL:jdbc:postgresql://localhost:5432/app}\n"
            "    username: ${DATABASE_USER:app}\n"
            "    password: ${DATABASE_PASSWORD:changeme}\n"
            "    driver-class-name: org.postgresql.Driver\n"
            "  jpa:\n"
            "    hibernate:\n"
            "      ddl-auto: validate\n"
        )
    redis_block = ""
    if spec.requires_redis:
        redis_block = (
            "  data:\n"
            "    redis:\n"
            "      host: ${REDIS_HOST:localhost}\n"
            "      port: ${REDIS_PORT:6379}\n"
        )
    return f"""# Auto-gerado pelo GCA. [gca:auto]
spring:
  application:
    name: {spec.project_slug}
{db_block}{redis_block}
server:
  port: ${{PORT:8080}}

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
"""


def _security_config_kt(spec: ScaffoldSpec) -> str:
    cls = _class_name_from_slug(spec.project_slug)
    return f"""// Auto-gerado pelo GCA — ajuste regras conforme RBAC do projeto. [gca:auto]
package {spec.package}.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.security.config.annotation.web.builders.HttpSecurity
import org.springframework.security.web.SecurityFilterChain

@Configuration
open class {cls}SecurityConfig {{

    @Bean
    open fun filterChain(http: HttpSecurity): SecurityFilterChain {{
        http
            .authorizeHttpRequests {{ auth ->
                auth
                    .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                    .anyRequest().authenticated()
            }}
            .httpBasic {{ }}
        return http.build()
    }}
}}
"""


def _application_tests_kt(spec: ScaffoldSpec) -> str:
    cls = _class_name_from_slug(spec.project_slug) + "Application"
    return f"""// Auto-gerado pelo GCA — smoke test do contexto Spring. [gca:auto]
package {spec.package}

import org.junit.jupiter.api.Test
import org.springframework.boot.test.context.SpringBootTest

@SpringBootTest
class {cls}Tests {{

    @Test
    fun contextLoads() {{
    }}
}}
"""


def _gitignore_kotlin() -> str:
    return """# Auto-gerado pelo GCA. [gca:auto]
.gradle/
build/
out/
!**/src/main/**/build/
!**/src/test/**/build/

# IDE
.idea/
*.iml
.vscode/

# Kotlin
*.class

# OS
.DS_Store
"""


def _readme(spec: ScaffoldSpec) -> str:
    db = f"- {spec.database} (Spring Data JPA + driver postgres)" if (spec.database or "").lower().startswith("postgres") else ""
    redis = "- Redis (Spring Data Redis)" if spec.requires_redis else ""
    sec = "- Spring Security" if spec.requires_security else ""
    return f"""# {spec.project_name}

> Scaffold inicial **Kotlin / Spring Boot 3** gerado pelo GCA.

## Stack

- Kotlin {_KOTLIN_VERSION}
- Spring Boot {spec.framework_version or _SPRING_BOOT_VERSION}
- Java {spec.java_version} (JVM target)
- Gradle Kotlin DSL
{db}
{redis}
{sec}

## Como rodar

```bash
./gradlew bootRun
```

App em `http://localhost:8080`. Health: `/actuator/health`.

## Testes

```bash
./gradlew test
```
"""


def scaffold_kotlin_spring(spec: ScaffoldSpec) -> List[ScaffoldFile]:
    """Gera estrutura inicial de um app Kotlin + Spring Boot 3 + Gradle KTS."""
    pkg_path = _package_to_path(spec.package)
    files: List[ScaffoldFile] = [
        ScaffoldFile("build.gradle.kts", _build_gradle_kts(spec)),
        ScaffoldFile("settings.gradle.kts", _settings_gradle_kts(spec)),
        ScaffoldFile(".gitignore", _gitignore_kotlin()),
        ScaffoldFile("README.md", _readme(spec)),
        ScaffoldFile(
            f"src/main/kotlin/{pkg_path}/{_class_name_from_slug(spec.project_slug)}Application.kt",
            _application_kt(spec),
        ),
        ScaffoldFile(
            "src/main/resources/application.yml",
            _application_yml(spec),
        ),
        ScaffoldFile(
            f"src/test/kotlin/{pkg_path}/{_class_name_from_slug(spec.project_slug)}ApplicationTests.kt",
            _application_tests_kt(spec),
        ),
    ]
    if spec.requires_security:
        files.append(
            ScaffoldFile(
                f"src/main/kotlin/{pkg_path}/config/{_class_name_from_slug(spec.project_slug)}SecurityConfig.kt",
                _security_config_kt(spec),
            )
        )
    return files

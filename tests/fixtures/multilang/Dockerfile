FROM causaltrace-multilang-runner:local
USER root
WORKDIR /opt
RUN npm install vitest@4 jest@30
WORKDIR /opt/maven-fixture
COPY pom.xml ./
COPY src ./src
RUN mvn -B -Dmaven.repo.local=/opt/maven-repository test && chmod -R a+rX /opt/maven-repository
USER runner
WORKDIR /workspace

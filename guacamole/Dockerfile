# Start from Tomcat image
FROM tomcat:8.0.53-jre8

# Environment variables
ENV BUILD_DIR=/tmp/hastexo-xblock-BUILD \
    BUILD_DEPS="maven openjdk-8-jdk-headless" \
    RUN_DIR=/opt/hastexo-xblock \
    WAR_FILE=hastexo-xblock.war

# Add configuration scripts
COPY bin $RUN_DIR/bin/

# Copy source to build directory
COPY . $BUILD_DIR

# Build app
RUN apt-get update && \
    apt-get install -y --no-install-recommends $BUILD_DEPS && \
    /opt/hastexo-xblock/bin/build-app.sh && \
    rm -Rf $BUILD_DIR && \
    rm -Rf /var/lib/apt/lists/* && \
    apt-get purge -y --auto-remove $BUILD_DEPS

# Start hastexo-xblock under tomcat, listening on 0.0.0.0:8080
EXPOSE 8080
CMD ["/opt/hastexo-xblock/bin/start-app.sh"]

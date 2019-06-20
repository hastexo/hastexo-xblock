#!/bin/sh -e

# Create run directory
mkdir -p "${RUN_DIR}"
cd "${BUILD_DIR}"

# Build war file
mvn package
rm -fR ~/.m2

# Copy war file to destination
cp target/*.war "${RUN_DIR}/${WAR_FILE}"

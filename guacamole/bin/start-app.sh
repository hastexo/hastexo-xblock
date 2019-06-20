#!/bin/sh -e

# Install webapp
ln -sf ${RUN_DIR}/${WAR_FILE} /usr/local/tomcat/webapps/

# Configure guacd
export GUACD_HOSTNAME=guacd
export GUACD_PORT=4822

# Start tomcat
cd /usr/local/tomcat
exec catalina.sh run

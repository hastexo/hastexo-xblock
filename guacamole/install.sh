#!/bin/bash -ex

GUACAMOLE_VERSION="0.9.13"
HASTEXO_VERSION=$(cd..;python setup.py --version)

# Install requirements
apt update
apt install -y \
	build-essential \
	libcairo2-dev \
	libjpeg-turbo8-dev \
	libpng12-dev \
	libossp-uuid-dev \
	libfreerdp-dev \
	libpango1.0-dev \
	libssh2-1-dev \
	libvncserver-dev \
	libssl-dev \
	libwebp-dev \
	tomcat8 \
	freerdp \
	openjdk-8-jdk-headless \
	maven \
	curl \
	jq

# Download server tarball
SERVER=$(curl -s 'https://www.apache.org/dyn/closer.cgi?as_json=1' | jq --raw-output '.preferred|rtrimstr("/")')
wget ${SERVER}/incubator/guacamole/${GUACAMOLE_VERSION}-incubating/source/guacamole-server-${GUACAMOLE_VERSION}-incubating.tar.gz
tar -xzf guacamole-server-${GUACAMOLE_VERSION}-incubating.tar.gz

# Compile and install server
cd guacamole-server-${GUACAMOLE_VERSION}-incubating
./configure --with-init-dir=/etc/init.d
make
make install
ln -s /usr/local/lib/freerdp/* /usr/lib/x86_64-linux-gnu/freerdp/.
ldconfig
systemctl enable guacd
cd ..

# Cleanup
rm -f guacamole-server-${GUACAMOLE_VERSION}-incubating.tar.gz
rm -fr guacamole-server-${GUACAMOLE_VERSION}-incubating/

# Build app and deploy it
mvn package
cp target/hastexo-xblock-${HASTEXO_VERSION}.war /var/lib/tomcat8/webapps/hastexo-xblock.war
systemctl restart tomcat8

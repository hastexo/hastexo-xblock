#!/bin/sh -e

GUACD_VERSION="0.9.13"

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
	freerdp

# Download server tarball
wget ${SERVER}http://archive.apache.org/dist/guacamole/${GUACD_VERSION}-incubating/source/guacamole-server-${GUACD_VERSION}-incubating.tar.gz
tar -xzf guacamole-server-${GUACD_VERSION}-incubating.tar.gz

# Compile and install server
cd guacamole-server-${GUACD_VERSION}-incubating
./configure --with-init-dir=/etc/init.d
make
make install
ln -s /usr/local/lib/freerdp/* /usr/lib/x86_64-linux-gnu/freerdp/.
ldconfig
systemctl enable guacd
cd ..

# Cleanup
rm -f guacamole-server-${GUACD_VERSION}-incubating.tar.gz
rm -fr guacamole-server-${GUACD_VERSION}-incubating/

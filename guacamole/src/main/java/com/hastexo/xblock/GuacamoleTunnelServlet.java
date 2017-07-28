package com.hastexo.xblock;

import javax.servlet.http.HttpServletRequest;
import org.apache.guacamole.GuacamoleException;
import org.apache.guacamole.net.GuacamoleSocket;
import org.apache.guacamole.net.GuacamoleTunnel;
import org.apache.guacamole.net.InetGuacamoleSocket;
import org.apache.guacamole.net.SimpleGuacamoleTunnel;
import org.apache.guacamole.protocol.ConfiguredGuacamoleSocket;
import org.apache.guacamole.protocol.GuacamoleClientInformation;
import org.apache.guacamole.protocol.GuacamoleConfiguration;
import org.apache.guacamole.servlet.GuacamoleHTTPTunnelServlet;

public class GuacamoleTunnelServlet extends GuacamoleHTTPTunnelServlet {

    @Override
    protected GuacamoleTunnel doConnect(HttpServletRequest request) throws GuacamoleException {

        // guacd connection information
        String hostname = "localhost";
        int port = 4822;

        // SSH connection information
        GuacamoleConfiguration config = new GuacamoleConfiguration();
        config.setProtocol("ssh");
        config.setParameter("hostname", request.getParameter("ip"));
        config.setParameter("port", "22");
        config.setParameter("username", request.getParameter("user"));
        config.setParameter("private-key", request.getParameter("key"));
        GuacamoleClientInformation info = new GuacamoleClientInformation();
        info.setOptimalScreenWidth(860);
        info.setOptimalScreenHeight(320);

        // Connect to guacd, proxying a connection to the VNC server above
        GuacamoleSocket socket = new ConfiguredGuacamoleSocket(
            new InetGuacamoleSocket(hostname, port),
            config,
            info
        );

        // Create tunnel from now-configured socket
        GuacamoleTunnel tunnel = new SimpleGuacamoleTunnel(socket);
        return tunnel;
    }
}

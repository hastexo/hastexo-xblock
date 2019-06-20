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

public class HastexoHTTPTunnelServlet extends GuacamoleHTTPTunnelServlet {

    @Override
    protected GuacamoleTunnel doConnect(HttpServletRequest request) throws GuacamoleException {

        // guacd connection information
        String guacd_hostname = System.getenv("GUACD_HOSTNAME");
        if (guacd_hostname == null) guacd_hostname = "localhost";

        int guacd_port;
        try {
            guacd_port = Integer.parseInt(System.getenv("GUACD_PORT"));
        }
        catch (NumberFormatException e)
        {
           guacd_port = 4822;
        }

        String protocol = request.getParameter("protocol");

        // Connection configuration
        GuacamoleConfiguration config = new GuacamoleConfiguration();
        if (protocol.equals("vnc")) {
            config.setProtocol("vnc");
            config.setParameter("hostname", request.getParameter("ip"));
            config.setParameter("port", "5901");
            config.setParameter("password", request.getParameter("password"));
        } else {
            config.setProtocol("ssh");
            config.setParameter("hostname", request.getParameter("ip"));
            config.setParameter("port", "22");
            config.setParameter("username", request.getParameter("user"));
            config.setParameter("private-key", request.getParameter("key"));
        }

        // Set screen size
        GuacamoleClientInformation info = new GuacamoleClientInformation();
        info.setOptimalScreenWidth(860);
        info.setOptimalScreenHeight(320);

        // Connect to guacd, proxying a connection to the VNC server above
        GuacamoleSocket socket = new ConfiguredGuacamoleSocket(
            new InetGuacamoleSocket(guacd_hostname, guacd_port),
            config,
            info
        );

        // Create tunnel from now-configured socket
        GuacamoleTunnel tunnel = new SimpleGuacamoleTunnel(socket);
        return tunnel;
    }
}

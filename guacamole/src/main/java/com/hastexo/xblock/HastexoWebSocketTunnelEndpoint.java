package com.hastexo.xblock;

import com.hastexo.xblock.HastexoTunnelRequest;
import java.util.Map;
import javax.websocket.Session;
import javax.websocket.EndpointConfig;
import javax.websocket.HandshakeResponse;
import javax.websocket.server.HandshakeRequest;
import javax.websocket.server.ServerEndpointConfig;
import org.apache.guacamole.GuacamoleException;
import org.apache.guacamole.net.GuacamoleSocket;
import org.apache.guacamole.net.GuacamoleTunnel;
import org.apache.guacamole.net.InetGuacamoleSocket;
import org.apache.guacamole.net.SimpleGuacamoleTunnel;
import org.apache.guacamole.protocol.ConfiguredGuacamoleSocket;
import org.apache.guacamole.protocol.GuacamoleClientInformation;
import org.apache.guacamole.protocol.GuacamoleConfiguration;
import org.apache.guacamole.websocket.GuacamoleWebSocketTunnelEndpoint;

public class HastexoWebSocketTunnelEndpoint extends GuacamoleWebSocketTunnelEndpoint {
    private static final String TUNNEL_REQUEST_PROPERTY = "WS_GUAC_TUNNEL_REQUEST";

    public static class Configurator extends ServerEndpointConfig.Configurator {

        @Override
        public void modifyHandshake(ServerEndpointConfig config,
                HandshakeRequest request, HandshakeResponse response) {

            super.modifyHandshake(config, request, response);

            // Store request for retrieval upon WebSocket open
            Map<String, Object> userProperties = config.getUserProperties();
            userProperties.clear();
            userProperties.put(TUNNEL_REQUEST_PROPERTY,
                    new HastexoWebSocketTunnelRequest(request));
        }
    }

    @Override
    protected GuacamoleTunnel createTunnel(Session session,
            EndpointConfig endpointConfig) throws GuacamoleException {

        Map<String, Object> userProperties = endpointConfig.getUserProperties();

        // Get original tunnel request
        HastexoTunnelRequest request = (HastexoTunnelRequest)
                userProperties.get(TUNNEL_REQUEST_PROPERTY);

        if (request == null)
            return null;

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

        // Request parameters
        String protocol = request.getParameter("protocol");
        String ip = request.getParameter("ip");
        String port = request.getParameter("port");
        String user = request.getParameter("user");
        String password = request.getParameter("password");
        String key = request.getParameter("key");
        int width = request.getIntegerParameter("width");
        int height = request.getIntegerParameter("height");
        String colorScheme = request.getParameter("color_scheme");
        String fontName = request.getParameter("font_name");
        String fontSize = request.getParameter("font_size");

        // Connection configuration
        GuacamoleConfiguration guacConfig = new GuacamoleConfiguration();
        guacConfig.setProtocol(protocol);
        guacConfig.setParameter("hostname", ip);
        guacConfig.setParameter("username", user);
        if (protocol.equals("rdp")) {
            if (port != null && !port.isEmpty()) {
                guacConfig.setParameter("port", port);
            } else {
                guacConfig.setParameter("port", "3389");
            }
            guacConfig.setParameter("password", password);
        } else if (protocol.equals("vnc")) {
            if (port != null && !port.isEmpty()) {
                guacConfig.setParameter("port", port);
            } else {
                guacConfig.setParameter("port", "5901");
            }
            guacConfig.setParameter("password", password);
            guacConfig.setParameter("encodings", "zrle ultra copyrect hextile zlib corre rre raw");
        } else {
            guacConfig.setParameter("private-key", key);
            guacConfig.setParameter("color-scheme", colorScheme);
            guacConfig.setParameter("font-name", fontName);
            guacConfig.setParameter("font-size", fontSize);
        }

        // Set screen size
        GuacamoleClientInformation info = new GuacamoleClientInformation();
        info.setOptimalScreenWidth(width);
        info.setOptimalScreenHeight(height);

        // Connect to guacd
        GuacamoleSocket socket = new ConfiguredGuacamoleSocket(
            new InetGuacamoleSocket(guacd_hostname, guacd_port),
            guacConfig,
            info
        );

        // Create tunnel from now-configured socket
        GuacamoleTunnel tunnel = new SimpleGuacamoleTunnel(socket);
        return tunnel;
    }
}

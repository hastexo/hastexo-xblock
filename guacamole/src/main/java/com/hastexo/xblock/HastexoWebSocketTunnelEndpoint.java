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
        String hostname = "localhost";
        int port = 4822;
        String protocol = request.getParameter("protocol");

        // Connection configuration
        GuacamoleConfiguration guacConfig = new GuacamoleConfiguration();
        if (protocol.equals("rdp")) {
            guacConfig.setProtocol("rdp");
            guacConfig.setParameter("hostname", request.getParameter("ip"));
            guacConfig.setParameter("username", request.getParameter("user"));
            guacConfig.setParameter("password", request.getParameter("password"));
        } else {
            guacConfig.setProtocol("ssh");
            guacConfig.setParameter("hostname", request.getParameter("ip"));
            guacConfig.setParameter("username", request.getParameter("user"));
            guacConfig.setParameter("private-key", request.getParameter("key"));
        }

        // Set screen size
        GuacamoleClientInformation info = new GuacamoleClientInformation();
        info.setOptimalScreenWidth(860);
        info.setOptimalScreenHeight(320);

        // Connect to guacd
        GuacamoleSocket socket = new ConfiguredGuacamoleSocket(
            new InetGuacamoleSocket(hostname, port),
            guacConfig,
            info
        );

        // Create tunnel from now-configured socket
        GuacamoleTunnel tunnel = new SimpleGuacamoleTunnel(socket);
        return tunnel;
    }
}

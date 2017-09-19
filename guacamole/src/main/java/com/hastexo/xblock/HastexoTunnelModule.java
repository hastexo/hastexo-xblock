package com.hastexo.xblock;

import com.hastexo.xblock.HastexoHTTPTunnelServlet;
import com.hastexo.xblock.HastexoWebSocketTunnelEndpoint;
import com.google.inject.servlet.ServletModule;
import com.google.inject.Scopes;
import java.util.Arrays;
import javax.websocket.DeploymentException;
import javax.websocket.server.ServerContainer;
import javax.websocket.server.ServerEndpointConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class HastexoTunnelModule extends ServletModule {

    private final Logger logger = LoggerFactory.getLogger(HastexoTunnelModule.class);

    @Override
    protected void configureServlets() {

        // Set up HTTP tunnel
        bind(HastexoHTTPTunnelServlet.class).in(Scopes.SINGLETON);
        serve("/http-tunnel").with(HastexoHTTPTunnelServlet.class);

        // Set up WebSocket tunnel
        ServerContainer container = (ServerContainer) getServletContext().getAttribute("javax.websocket.server.ServerContainer"); 
        if (container == null) {
            logger.warn("ServerContainer attribute required by JSR-356 is missing. Cannot load JSR-356 WebSocket support.");
            return;
        }

        // Build configuration for WebSocket tunnel
        ServerEndpointConfig config =
                ServerEndpointConfig.Builder.create(HastexoWebSocketTunnelEndpoint.class, "/websocket-tunnel")
                                            .configurator(new HastexoWebSocketTunnelEndpoint.Configurator())
                                            .subprotocols(Arrays.asList(new String[]{"guacamole"}))
                                            .build();

        try {
            // Add configuration to container
            container.addEndpoint(config);
        }
        catch (DeploymentException e) {
            logger.error("Unable to deploy WebSocket tunnel.", e);
        }
    }
}

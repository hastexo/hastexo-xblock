package com.hastexo.xblock;

import java.util.List;
import java.util.Map;
import javax.websocket.server.HandshakeRequest;
import com.hastexo.xblock.HastexoTunnelRequest;

public class HastexoWebSocketTunnelRequest extends HastexoTunnelRequest {

    private final Map<String, List<String>> handshakeParameters;

    public HastexoWebSocketTunnelRequest(HandshakeRequest request) {
        this.handshakeParameters = request.getParameterMap();
    }

    @Override
    public String getParameter(String name) {

        // Pull list of values, if present
        List<String> values = getParameterValues(name);
        if (values == null || values.isEmpty())
            return null;

        // Return first parameter value arbitrarily
        return values.get(0);
    }

    @Override
    public List<String> getParameterValues(String name) {
        return handshakeParameters.get(name);
    }
}

package com.hastexo.xblock;

import java.util.List;
import org.apache.guacamole.GuacamoleException;

public abstract class HastexoTunnelRequest {

    public static final String WIDTH_PARAMETER = "GUAC_WIDTH";
    public static final String HEIGHT_PARAMETER = "GUAC_HEIGHT";
    public static final String DPI_PARAMETER = "GUAC_DPI";

    public abstract String getParameter(String name);
    public abstract List<String> getParameterValues(String name);

    public Integer getIntegerParameter(String name) throws GuacamoleException {
        // Pull requested parameter
        String value = getParameter(name);
        if (value == null)
            return null;

        return Integer.parseInt(value);
    }

    public Integer getWidth() throws GuacamoleException {
        return getIntegerParameter(WIDTH_PARAMETER);
    }

    public Integer getHeight() throws GuacamoleException {
        return getIntegerParameter(HEIGHT_PARAMETER);
    }

    public Integer getDPI() throws GuacamoleException {
        return getIntegerParameter(DPI_PARAMETER);
    }
}

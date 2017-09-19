package com.hastexo.xblock;

import com.hastexo.xblock.HastexoTunnelModule;
import com.google.inject.Guice;
import com.google.inject.Injector;
import com.google.inject.servlet.GuiceServletContextListener;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class HastexoServletContextListener extends GuiceServletContextListener {

    private final Logger logger = LoggerFactory.getLogger(HastexoServletContextListener.class);

    @Override
    protected Injector getInjector() {
        return Guice.createInjector(new HastexoTunnelModule());
    }
}

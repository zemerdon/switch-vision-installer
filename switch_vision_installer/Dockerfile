FROM ghcr.io/home-assistant/base@sha256:94ff231402a5e7ad2a82e261ad5fa4ffae7d7bb095c3febb2edbdf309c9b6aca

ARG BUILD_VERSION
ARG BUILD_ARCH
ENV SV_INSTALLER_VERSION=${BUILD_VERSION}

LABEL \
  io.hass.name="Switch Vision Installer" \
  io.hass.description="Install and update Switch Vision from the official release repository" \
  io.hass.type="app" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 ca-certificates

COPY run.sh /run.sh
COPY app /opt/switch-vision-installer/app
COPY www /opt/switch-vision-installer/www
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

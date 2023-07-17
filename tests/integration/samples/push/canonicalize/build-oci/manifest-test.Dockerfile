FROM --platform=$TARGETPLATFORM alpine:latest
ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG MANIFESTTYPE="Unknown"

# Create some layers:
RUN apk add --no-cache python3
RUN apk add --no-cache py3-pip
# RUN apk add --no-cache py3-flask-restful
# RUN apk add --no-cache py3-requests

RUN echo "Building on $BUILDPLATFORM to run on $TARGETPLATFORM"
RUN mkdir -p bin/ && \
    echo "#!/bin/sh" > /bin/run.sh && \
    echo "echo 'Built on $BUILDPLATFORM to run on $TARGETPLATFORM, $MANIFESTTYPE manifest.'" >> /bin/run.sh && \
    echo "sleep 10m" >> /bin/run.sh && \
    chmod a+x /bin/run.sh

CMD /bin/run.sh

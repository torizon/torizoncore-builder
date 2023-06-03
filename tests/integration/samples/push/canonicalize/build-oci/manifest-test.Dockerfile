FROM --platform=$TARGETPLATFORM alpine:latest
ARG TARGETPLATFORM
ARG BUILDPLATFORM

# Create some layers:
RUN apk add --no-cache python3
RUN apk add --no-cache py3-pip
# RUN apk add --no-cache py3-flask-restful
# RUN apk add --no-cache py3-requests

RUN echo "Building on $BUILDPLATFORM to run on $TARGETPLATFORM"
RUN mkdir -p bin/ && \
    echo -e "#!/bin/sh\n\necho 'Built on $BUILDPLATFORM to run on $TARGETPLATFORM'" > /bin/run.sh && \
    chmod a+x /bin/run.sh

FROM golang:1.24.2-alpine

# install git
RUN --mount=type=cache,target=/var/cache/apk \
    apk update && apk upgrade && \
    apk add --cache-dir=/var/cache/apk bash git openssh

# install minica
RUN --mount=type=cache,target=/go/pkg/mod \
    go install github.com/jsha/minica@latest

# Declare an unprivileged user
ARG CA_USER=ca

# Create a user 'lm' with HOME at /lm
RUN addgroup -S ${CA_USER} && adduser -S ${CA_USER} -G ${CA_USER}

# create and set permissions
RUN mkdir /certs && chown -R ${CA_USER}:${CA_USER} /certs

# Set the user
USER ${CA_USER}

# set work dir
WORKDIR /certs

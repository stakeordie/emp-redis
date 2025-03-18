# Testing Workers with Production Hub

This directory contains configuration for testing workers with the production Redis hub.

## Setup

1. First, start the production hub:
   ```
   docker-compose up -d
   ```

2. Create the external network if it doesn't exist:
   ```
   docker network create redis_network
   ```

3. Set the authentication token (must match the one used by the hub):
   ```
   export WEBSOCKET_AUTH_TOKEN=your-secure-token-here
   ```

4. Start the test workers:
   ```
   docker-compose -f docker-compose.workers.yml up -d
   ```

## Configuration

### Connecting to a Remote Hub

To connect to a remote production hub (not running on localhost):

1. Edit `docker-compose.workers.yml` and change the `REDIS_API_HOST` value to your production hub's hostname or IP address.

2. Make sure the authentication token matches the one set on the production hub.

3. If the hub is on a different network, remove the `external: true` from the networks section.

## Monitoring

You can check the worker logs to see if they're connecting properly:

```
docker-compose -f docker-compose.workers.yml logs -f
```

## Scaling

You can scale the number of workers up or down:

```
docker-compose -f docker-compose.workers.yml up -d --scale worker1=1 --scale worker2=1 --scale worker3=0 --scale worker4=0
```

This would start only worker1 and worker2.

## Cleanup

To stop the test workers:

```
docker-compose -f docker-compose.workers.yml down
```

# SCNet container API handoff

This is a design and operations note for the optional SCNet container backend.
Credentials are never stored in this repository.

## Credential requirements

Use the existing SCNet skill/credential store. Depending on the local integration,
credentials may be supplied by macOS Keychain, Linux Secret Service, or environment
variables:

```text
SCNET_OPENAPI_USER
SCNET_OPENAPI_ACCESS_KEY
SCNET_OPENAPI_SECRET_KEY
```

Never commit these variables or their values.

## Relevant API lifecycle

The container manager implemented by the local SCNet skill uses:

```text
POST   /ai/openapi/v2/instance-service/task
POST   /ai/openapi/v2/instance-service/task/actions/restart
POST   /ai/openapi/v2/instance-service/task/actions/stop
DELETE /ai/openapi/v2/instance-service/task
GET    /ai/openapi/v2/instance-service/task/list
GET    /ai/openapi/v2/instance-service/{id}/detail
GET    /ai/openapi/v2/instance-service/{id}/url
GET    /ai/openapi/v2/instance-service/resources
GET    /ai/openapi/v2/instance-service/resource-group
GET    /ai/openapi/v2/instance-service/allowed-mount-dir
POST   /ai/openapi/v2/image/images
```

The region-specific AI URL and token must come from the SCNet credential/region
discovery layer. Do not hardcode a token or assume every region uses the same hostname.

## Recommended lifecycle

1. Create one 14B service instance with a short walltime and a mounted model path.
2. Start it on the first request.
3. Poll detail status until `Running`.
4. Query its service URL.
5. Proxy OpenAI-compatible requests to the URL.
6. Stop on idle timeout.
7. Delete the instance only when the user asks to remove the saved template.

Do not create and delete an instance for every prompt; deployment and model-loading
latency defeats the API-like experience.

## Current validation status

Validated read-only operations:

- region/token authentication;
- resource groups;
- authorized mount paths;
- private/public image listing;
- container listing;
- container detail/URL endpoints.

Validated lifecycle operation:

- a previously terminated 1-DCU test instance accepted restart;
- it remained `Waiting` for approximately 270 seconds;
- it was stopped afterward and returned to `Terminated`.

No new instance was created and no container was left running. Before enabling this
backend in the client, confirm that the account has a nonzero DCU container limit and
that the desired resource group can schedule a 14B service.

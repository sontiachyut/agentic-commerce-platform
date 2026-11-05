import httpx

from commerce.simulator import SourceRequest


class SourceUnavailable(Exception):
    pass


class SourceConflict(Exception):
    pass


class HttpSource:
    def __init__(self, settings):
        self.client = httpx.Client(
            base_url=settings.simulator_url,
            timeout=5,
            headers={"Authorization": "Bearer " + settings.source_token.get_secret_value()},
            follow_redirects=False,
            trust_env=False,
        )

    def observe_or_send(self, request: SourceRequest):
        try:
            observed = self.client.get(f"/v1/commands/{request.execution_id}/{request.action}")
            if observed.status_code == 404:
                observed = self.client.post("/v1/commands", json=request.model_dump())
            if observed.status_code == 409:
                raise SourceConflict("Source rejected the command binding or transition")
            observed.raise_for_status()
            value = observed.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceUnavailable("Source result is unresolved") from exc
        if not isinstance(value, dict):
            raise SourceConflict("Invalid source observation shape")
        if value.get("workflow", "kiosk") != request.workflow:
            raise SourceConflict("Source observation belongs to another workflow")
        # Receiving valid JSON is not enough. Bind every observation to our command.
        if any(
            value.get(key) != expected
            for key, expected in {
                "execution_id": request.execution_id,
                "action": request.action,
                "amount_minor": request.amount_minor,
                "currency": request.currency,
                "quote_digest": request.quote_digest,
                "command_id": f"{request.execution_id}:{request.action}",
                "source": "local-stateful-simulator-v1",
            }.items()
        ):
            raise SourceConflict("Untrusted source observation")
        return value

    def close(self):
        self.client.close()

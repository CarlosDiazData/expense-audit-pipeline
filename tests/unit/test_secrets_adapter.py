from expense_audit.adapters.secrets import SecretAccessCodeProvider


class FakePayload:
    def __init__(self, data):
        self.data = data


class FakeResponse:
    def __init__(self, data):
        self.payload = FakePayload(data)


class FakeSecretClient:
    def __init__(self, value):
        self.value = value
        self.requests = []

    def access_secret_version(self, request):
        self.requests.append(request)
        return FakeResponse(self.value)


def test_reads_latest_secret_version_and_decodes():
    client = FakeSecretClient(b"super-secret-code\n")
    provider = SecretAccessCodeProvider(client, project="demo", secret_name="access-code")

    assert provider.get() == "super-secret-code"
    assert client.requests == [{"name": "projects/demo/secrets/access-code/versions/latest"}]


def test_caches_secret_value_between_calls():
    client = FakeSecretClient(b"code")
    provider = SecretAccessCodeProvider(client, project="demo", secret_name="access-code")

    provider.get()
    provider.get()

    assert len(client.requests) == 1

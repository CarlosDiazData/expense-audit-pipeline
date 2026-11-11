import pytest

from expense_audit.adapters.gcs import GcsStorage
from expense_audit.domain.errors import DocumentError


class FakeBlob:
    def __init__(self, name, store):
        self.name = name
        self.store = store
        self.content_type = store.get(name, (b"", "application/octet-stream"))[1]
        self.size = None
        self.uploaded = None

    def reload(self):
        if self.name not in self.store:
            raise FileNotFoundError(self.name)
        self.size = len(self.store[self.name][0])
        self.content_type = self.store[self.name][1]

    def download_as_bytes(self):
        return self.store[self.name][0]

    def upload_from_string(self, data, content_type=None):
        self.uploaded = (data, content_type)
        self.store[self.name] = (data, content_type)


class FakeBucket:
    def __init__(self, store):
        self.store = store

    def blob(self, name):
        return FakeBlob(name, self.store)


class FakeClient:
    def __init__(self, store):
        self.store = store
        self.bucket_names = []

    def bucket(self, name):
        self.bucket_names.append(name)
        return FakeBucket(self.store)


def storage(store=None):
    client = FakeClient(store if store is not None else {})
    return GcsStorage(client, bucket_name="landing-bucket"), client


def test_upload_writes_object_at_path():
    adapter, client = storage()

    adapter.upload("uploads/u1/ticket.pdf", b"%PDF-1.4", "application/pdf")

    assert client.bucket_names == ["landing-bucket"]
    assert client.store["uploads/u1/ticket.pdf"] == (b"%PDF-1.4", "application/pdf")


def test_download_returns_bytes_and_content_type():
    adapter, _ = storage({"uploads/u1/ticket.pdf": (b"%PDF-1.4", "application/pdf")})

    content, content_type = adapter.download("uploads/u1/ticket.pdf", max_bytes=1024)

    assert content == b"%PDF-1.4"
    assert content_type == "application/pdf"


def test_download_rejects_object_over_max_bytes():
    adapter, _ = storage({"uploads/u1/big.pdf": (b"x" * 11, "application/pdf")})

    with pytest.raises(DocumentError) as error:
        adapter.download("uploads/u1/big.pdf", max_bytes=10)

    assert error.value.code == "FILE_TOO_LARGE"


def test_unreadable_object_is_unsupported_document():
    adapter, _ = storage()

    with pytest.raises(DocumentError) as error:
        adapter.download("uploads/u1/missing.pdf", max_bytes=10)

    assert error.value.code == "UNSUPPORTED_DOCUMENT"

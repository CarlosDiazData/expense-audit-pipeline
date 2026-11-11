from unittest.mock import Mock

import pytest
from google.api_core.exceptions import ServiceUnavailable

from expense_audit.adapters.gcs import GcsStorage
from expense_audit.domain.errors import DocumentError


def test_transient_gcs_read_error_is_not_a_document_error():
    blob = Mock(size=None, content_type="application/pdf")
    blob.reload.side_effect = ServiceUnavailable("simulated GCS 503")
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    storage = GcsStorage(client, "landing-bucket")

    with pytest.raises(Exception) as error:
        storage.download("uploads/u1/ticket.pdf", max_bytes=1024)

    assert not isinstance(error.value, DocumentError)


def test_missing_object_is_still_a_document_error():
    from google.api_core.exceptions import NotFound

    blob = Mock(size=None, content_type="application/pdf")
    blob.reload.side_effect = NotFound("missing")
    client = Mock()
    client.bucket.return_value.blob.return_value = blob
    storage = GcsStorage(client, "landing-bucket")

    with pytest.raises(DocumentError) as error:
        storage.download("uploads/u1/ticket.pdf", max_bytes=1024)

    assert error.value.code == "UNSUPPORTED_DOCUMENT"

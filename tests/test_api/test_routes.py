import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "label-guardian-backend",
        "environment": "test",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_api_health_alias_uses_the_same_contract(client):
    root_response = await client.get("/health")
    api_response = await client.get("/api/health")
    v1_response = await client.get("/api/v1/health")

    assert api_response.status_code == 200
    assert api_response.json() == root_response.json()
    assert v1_response.status_code == 200
    assert v1_response.json() == root_response.json()


@pytest.mark.asyncio
async def test_readiness_checks_database(client):
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_openapi_identifies_label_guardian(client):
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    document = response.json()
    assert document["info"] == {
        "title": "Label Guardian API",
        "description": "QA orchestration API for 2D perception annotations",
        "version": "0.1.0",
    }
    assert "/api/v1/qa-cases" in document["paths"]
    assert "/api/v1/dataset/images/{split}/{image_id}/annotations" in document["paths"]
    assert not any("cvat" in path.lower() for path in document["paths"])
    assert "/api/v1/dataset/images" in document["paths"]
    assert "/api/v1/dataset/frame-samples" in document["paths"]
    assert "/api/v1/dataset/images/{split}/{image_id}/evaluate" in document["paths"]
    assert document["paths"]["/api/v1/ingestion/runs"]["get"]["security"] == [
        {"HTTPBearer": []}
    ]
    assert "/api/qa-cases" not in document["paths"]
    assert "/api/health" not in document["paths"]
    assert "/api/v1/chat" not in document["paths"]


@pytest.mark.asyncio
async def test_unversioned_routes_remain_compatibility_aliases(client):
    v1_response = await client.get("/api/v1/qa-cases?limit=1")
    legacy_response = await client.get("/api/qa-cases?limit=1")

    assert legacy_response.status_code == v1_response.status_code
    assert legacy_response.json() == v1_response.json()

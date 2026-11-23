"""Configuration uses the existing platform identity, with no role or second session gate."""
import hashlib
from datetime import datetime, timezone

import pytest
from fastapi import Depends

from app.core.permissions import RequireSystemPermission, RequireSpacePermission
from app.models.chatbi import ChatBIPPTModelConfig
from app.models.user import User
from tests.test_chatbi_credentials import api, ADMIN_PATH
from tests.test_chatbi_ppt_model import managed


ROLES = ['super_admin', 'admin', 'member', 'visitor']
OPERATOR = {'X-User-Id': '2'}


def operator(api, role):
    with api.factory() as db:
        user = db.get(User, 2)
        user.system_role = role
        user.password_hash = hashlib.sha256(b'member-password').hexdigest()
        db.commit()
    reply = api.client.post('/api/users/login', json={'username': 'member', 'password': 'member-password'})
    assert reply.status_code == 200
    api.client.cookies.clear()  # QA /chatbi/ paths never need a separate management cookie.


@pytest.mark.parametrize('role', ROLES)
@pytest.mark.parametrize('cookie', [None, 'expired-old-cookie', 'invalid-old-cookie'])
def test_every_logged_in_role_can_configure_keys_without_management_cookie(api, role, cookie):
    operator(api, role)
    if cookie:
        api.client.cookies.set('chatbi_key_admin', cookie, path='/api')
    assert api.client.get(ADMIN_PATH, headers=OPERATOR).status_code == 200
    assert api.client.get(ADMIN_PATH + '/workflow-options', headers=OPERATOR).status_code == 200
    reply = api.client.post(ADMIN_PATH, headers=OPERATOR, json={
        'name': '普通登录配置测试', 'environment': 'uat', 'workflow_id': 1, 'version_id': 11})
    assert reply.status_code == 201, reply.text
    key_id = reply.json()['data']['key']['id']
    assert api.client.put(ADMIN_PATH + '/' + key_id, headers=OPERATOR,
        json={'name': '已修改绑定', 'workflow_id': 1, 'version_id': 12, 'enabled': True}).status_code == 200
    assert api.client.patch(ADMIN_PATH + '/' + key_id + '/enabled', headers=OPERATOR,
        json={'enabled': False}).status_code == 200


@pytest.mark.parametrize('role', ROLES)
def test_all_roles_can_save_ai_ppt_model_and_share_configuration_entry(managed, role):
    from app.routers.chatbi.conversations import router as conversations
    from app.routers.data_sync import router as sync
    operator(managed, role)
    managed.client.app.include_router(conversations)
    managed.client.app.include_router(sync)
    assert managed.client.get('/api/chatbi/ppt-model', headers=OPERATOR).status_code == 200
    assert managed.client.get('/api/chatbi/ppt-model/options', headers=OPERATOR).status_code == 200
    saved = managed.client.put('/api/chatbi/ppt-model', headers=OPERATOR,
        json={'provider_id': 1, 'model': 'alpha'})
    assert saved.status_code == 200, saved.text
    with managed.factory() as db:
        assert db.get(ChatBIPPTModelConfig, 1).updated_by == 2
    assert managed.client.get('/api/chatbi/conversations', headers=OPERATOR).status_code == 200


@pytest.mark.parametrize('role', ROLES)
def test_actual_language_model_configuration_routes_allow_every_role(managed, role):
    from app.routers.model_provider.router import router
    operator(managed, role)
    managed.client.app.include_router(router)
    reply = managed.client.post('/api/model-providers', headers=OPERATOR, json={
        'name': '配置权限隔离验收', 'base_url': 'https://example.test/v1',
        'api_key': 'isolated-fake-model-key', 'models': '["local-test"]'})
    assert reply.status_code == 200, reply.text
    provider_id = reply.json()['data']['id']
    saved = managed.client.put('/api/model-providers/' + str(provider_id), headers=OPERATOR,
        json={'name': '任意登录角色均可保存'})
    assert saved.status_code == 200 and saved.json()['data']['name'] == '任意登录角色均可保存'


@pytest.mark.parametrize('role', ROLES)
def test_shared_model_and_space_config_dependencies_ignore_role(api, role):
    operator(api, role)
    @api.client.app.post('/api/config-test')
    def configure(user_id: int = Depends(RequireSystemPermission('*'))):
        return {'operator_id': user_id}
    @api.client.app.post('/api/spaces/{space_id}/config-test')
    def space_config(operator: tuple = Depends(RequireSpacePermission('space_member:add'))):
        return {'operator_id': operator[0], 'space_id': operator[1]}
    assert api.client.post('/api/config-test', headers=OPERATOR).status_code == 200
    reply = api.client.post('/api/spaces/99/config-test', headers=OPERATOR)
    assert reply.status_code == 200 and reply.json()['data'] == {'operator_id': 2, 'space_id': 99}


def test_member_can_configure_accounts_without_super_admin_role(api):
    from app.services.user.service import UserService
    from app.schemas.user import UserUpdate
    operator(api, 'member')
    with api.factory() as db:
        result = UserService.update_user(db, 1, UserUpdate(display_name='普通登录用户可修改展示名'), 2)
        assert result.display_name == '普通登录用户可修改展示名'
        result = UserService.update_user(db, 2, UserUpdate(system_role='admin'), 2)
        assert result.system_role == 'admin'


def test_member_can_configure_space_without_being_owner(api, monkeypatch):
    from app.models.space import Space
    from app.repositories.space.repository import SpaceRepository
    from app.services.space.service import SpaceService
    from app.schemas.space import SpaceUpdate
    operator(api, 'member')
    row = Space(id=99, name='测试空间', code='test99', is_active=True,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), settings={})
    monkeypatch.setattr(SpaceRepository, 'get_by_id', lambda *args: row)
    monkeypatch.setattr(SpaceRepository, 'get_by_code', lambda *args: None)
    def update(db, space_id, body):
        row.name = body.name
        return row
    monkeypatch.setattr(SpaceRepository, 'update', update)
    monkeypatch.setattr(SpaceRepository, 'get_user_role', lambda *args: 'visitor')
    with api.factory() as db:
        assert SpaceService.update_space(db, 99, SpaceUpdate(name='允许登录用户配置'), 2).name == '允许登录用户配置'


def test_configuration_accepts_the_normal_identity_but_still_uses_platform_login(api):
    operator(api, 'member')
    assert api.client.get(ADMIN_PATH, headers=OPERATOR).status_code == 200
    assert api.client.get(ADMIN_PATH).status_code == 401


def test_login_no_longer_issues_a_second_management_session(api):
    api.client.cookies.clear()
    reply = api.client.post('/api/users/login', json={'username': 'admin', 'password': 'test-admin-password'})
    assert reply.status_code == 200
    assert 'chatbi_key_admin=' not in reply.headers.get('set-cookie', '')


@pytest.mark.parametrize('role', ROLES)
def test_sync_configuration_uses_the_same_platform_login(api, role, monkeypatch):
    from app.routers.data_sync import router, service
    operator(api, role)
    api.client.app.include_router(router)
    monkeypatch.setattr(service, 'list_tasks', lambda db: [])
    requested = []
    def enqueue(db, task_id, *, requested_by):
        requested.append((task_id, requested_by))
        return {'id': 'isolated-sync-request', 'requested_by': requested_by}
    monkeypatch.setattr(service, 'enqueue', enqueue)
    assert api.client.get('/api/chatbi/data-sync/tasks', headers=OPERATOR).status_code == 200
    reply = api.client.post('/api/chatbi/data-sync/tasks/org/run', headers=OPERATOR)
    assert reply.status_code == 202 and requested == [('org', 2)]

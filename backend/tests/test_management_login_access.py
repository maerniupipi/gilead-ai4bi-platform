import hashlib

import pytest
from app.models.user import User
from app.routers.chatbi.conversations import router as conversations
from tests.test_chatbi_credentials import api


@pytest.mark.parametrize('role', ['super_admin', 'admin', 'member', 'visitor'])
def test_every_logged_in_role_can_manage_all_three_modules(api, role):
    from app.models.user_space_role import UserSpaceRole
    from app.models.user_space_last_access import UserSpaceLastAccess
    with api.factory() as db:
        for model in (UserSpaceRole, UserSpaceLastAccess):
            model.__table__.create(db.get_bind(), checkfirst=True)
    api.client.app.include_router(conversations)
    with api.factory() as db:
        user = db.get(User, 2)
        user.system_role = role
        user.password_hash = hashlib.sha256(b'member-password').hexdigest()
        db.commit()
    api.client.cookies.clear()
    logged_in = api.client.post('/api/users/login', json={'username': 'member', 'password': 'member-password'})
    assert logged_in.status_code == 200
    header = {'X-User-Id': '2'}
    for path in ['/api/users', '/api/users/1', '/api/chatbi/keys', '/api/chatbi/conversations']:
        assert api.client.get(path, headers=header).status_code == 200, path
    created = api.client.post('/api/users', headers=header,
                             json={'username': 'created-user', 'display_name': '新用户', 'password': 'some-password'})
    assert created.status_code == 200, created.text
    target = created.json()['data']['id']
    assert api.client.put(f'/api/users/{target}', headers=header, json={'is_active': False}).status_code == 200
    assert api.client.delete(f'/api/users/{target}', headers=header).status_code == 200
    key = api.client.post('/api/chatbi/keys', headers=header,
                         json={'name': '登录用户创建', 'environment': 'uat', 'workflow_id': 1, 'version_id': 11})
    assert key.status_code == 201
    key_id = key.json()['data']['key']['id']
    assert api.client.patch(f'/api/chatbi/keys/{key_id}/enabled', headers=header, json={'enabled': False}).status_code == 200


def test_user_management_uses_normal_login_without_a_second_cookie(api):
    assert api.client.get('/api/users', headers={'X-User-Id': '2'}).status_code == 200
    api.client.cookies.clear()
    for path in ['/api/users', '/api/users/1']:
        assert api.client.get(path, headers={'X-User-Id': '1'}).status_code == 200
        assert api.client.get(path).status_code == 401
    assert api.client.post('/api/users', json={'username': 'without-login'}).status_code == 401


def test_protected_accounts_remain_protected(api):
    assert api.client.delete('/api/users/1', headers={'X-User-Id': '1'}).status_code == 403
    assert api.client.put('/api/users/1', headers={'X-User-Id': '1'}, json={'is_active': False}).status_code == 400


@pytest.mark.parametrize('role', ['admin', 'super_admin'])
def test_logged_in_user_can_configure_account_roles(api, role):
    with api.factory() as db:
        member = db.get(User, 2)
        member.password_hash = hashlib.sha256(b'member-password').hexdigest()
        db.commit()
    api.client.cookies.clear()
    assert api.client.post('/api/users/login', json={'username': 'member', 'password': 'member-password'}).status_code == 200
    assert api.client.get('/api/users', headers={'X-User-Id': '2'}).status_code == 200
    assert api.client.put('/api/users/2', headers={'X-User-Id': '2'}, json={'system_role': role}).status_code == 200

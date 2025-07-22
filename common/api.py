import jwt
import os
import requests
from datetime import datetime, timedelta, UTC
from typing import Any, Optional

from openpilot.system.hardware.hw import Paths
from openpilot.system.version import get_version

API_HOST: str = os.getenv('API_HOST', 'https://api.commadotai.com')


class Api:
  dongle_id: str
  private_key: str

  def __init__(self, dongle_id: str) -> None:
    self.dongle_id = dongle_id
    # TODO: use Paths.id_rsa() once merged
    with open(Paths.persist_root() + '/comma/id_rsa') as f:
      self.private_key = f.read()

  def get(self, endpoint: str, timeout: Optional[int] = None, access_token: Optional[str] = None, **params: Any) -> requests.Response:
    return self.request('GET', endpoint, timeout=timeout, access_token=access_token, **params)

  def post(self, endpoint: str, timeout: Optional[int] = None, access_token: Optional[str] = None, **params: Any) -> requests.Response:
    return self.request('POST', endpoint, timeout=timeout, access_token=access_token, **params)

  def request(self, method: str, endpoint: str, timeout: Optional[int] = None, access_token: Optional[str] = None, **params: Any) -> requests.Response:
    return api_get(endpoint, method=method, timeout=timeout, access_token=access_token, **params)

  def get_token(self, expiry_hours: int = 1) -> str:
    now: datetime = datetime.now(UTC).replace(tzinfo=None)
    payload: dict[str, Any] = {
      'identity': self.dongle_id,
      'nbf': now,
      'iat': now,
      'exp': now + timedelta(hours=expiry_hours)
    }
    token: str | bytes = jwt.encode(payload, self.private_key, algorithm='RS256')
    if isinstance(token, bytes):
      return token.decode('utf8')
    return token


def api_get(endpoint: str, method: str = 'GET', timeout: Optional[int] = None, access_token: Optional[str] = None, **params: Any) -> requests.Response:
  headers: dict[str, str] = {}
  if access_token is not None:
    headers['Authorization'] = "JWT " + access_token

  headers['User-Agent'] = "openpilot-" + get_version()

  return requests.request(method, API_HOST + "/" + endpoint, timeout=timeout, headers=headers, params=params)

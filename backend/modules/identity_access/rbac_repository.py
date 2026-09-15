"""Compatibility facade — prefer repository_rbac.RbacRepositoryMixin."""

from __future__ import annotations

from backend.modules.identity_access.repository_rbac import RbacRepositoryMixin

RolePermissionRepositoryMixin = RbacRepositoryMixin

__all__ = ["RbacRepositoryMixin", "RolePermissionRepositoryMixin"]

"""Repository layer — every DB read/write goes through here.

These classes always receive `tenant_id` explicitly and never trust a query
parameter. Route code that "wants the current user's alerts" must call the
auth dependency first and pass `tenant_id` in. This is the only safety net
between tenants on shared infrastructure.
"""

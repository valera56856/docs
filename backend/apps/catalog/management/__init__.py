"""Management package for the catalog app.

Holds Django management commands (under ``commands/``) that operate on the
catalog cache — currently the ``sync_catalog`` command that refreshes
:class:`~apps.catalog.models.OurProduct` from the SalesDrive YML export.
"""

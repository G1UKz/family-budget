from alembic import context

import app.models  # noqa: F401  (register tables)
from app.db import Base, get_engine

target_metadata = Base.metadata

with get_engine().connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

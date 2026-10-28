from alembic import context
from sqlalchemy import MetaData, create_engine

from helper_bot.config import Settings

metadata = MetaData()

if context.is_offline_mode():
    context.configure(url=Settings().database_url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(Settings().database_url, connect_args={"connect_timeout": 5})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()

import os

# Importing app.db builds the engine from settings, and CI has no .env. Building it does not
# connect; a test that does connect must use sentinela_test, never sentinela.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://sentinela:sentinela@localhost:5432/sentinela_test",
)

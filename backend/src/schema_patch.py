"""演示库轻量补列：项目不引入迁移工具，create_all 只建新表不补旧表列。
仅在列缺失时 ALTER TABLE ADD COLUMN，幂等且不动既有数据。"""
from sqlalchemy import text,inspect
from .database import engine

SWATCH_COLUMNS={
    'withdrawn':'BOOLEAN NOT NULL DEFAULT FALSE',
    'withdrawn_by':"VARCHAR(120) NOT NULL DEFAULT ''",
    'withdraw_reason':"VARCHAR(300) NOT NULL DEFAULT ''",
    'withdrawn_at':'TIMESTAMP NULL',
    'source_version':'INTEGER NOT NULL DEFAULT 1',
    'source_updated_at':'TIMESTAMP NULL',
}
def ensure_columns():
    inspector=inspect(engine)
    if 'swatches' not in inspector.get_table_names():return
    existing={col['name'] for col in inspector.get_columns('swatches')}
    with engine.begin() as conn:
        for name,ddl in SWATCH_COLUMNS.items():
            if name in existing:continue
            conn.execute(text(f'ALTER TABLE swatches ADD COLUMN {name} {ddl}'))

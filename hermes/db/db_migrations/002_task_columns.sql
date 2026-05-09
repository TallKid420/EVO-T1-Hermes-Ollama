-- additional task metadata columns

ALTER TABLE tasks ADD COLUMN parent_agent TEXT;
ALTER TABLE tasks ADD COLUMN spawn_depth INTEGER DEFAULT 0;
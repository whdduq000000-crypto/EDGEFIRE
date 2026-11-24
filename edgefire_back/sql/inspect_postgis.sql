-- Read-only verification after backend starts; run in PostgreSQL.
SELECT version(), postgis_full_version();
SELECT tablename,indexname,indexdef FROM pg_indexes WHERE tablename IN ('sensor_nodes','wui_zones','telemetry_gas_logs','forecast_polygons','telemetry') ORDER BY tablename,indexname;
SELECT * FROM pg_partition_tree('telemetry_gas_logs');
EXPLAIN (ANALYZE,BUFFERS) SELECT node_id FROM sensor_nodes WHERE ST_DWithin(location::geography,ST_SetSRID(ST_MakePoint(127.76,37.88),4326)::geography,1000) ORDER BY location::geography <-> ST_SetSRID(ST_MakePoint(127.76,37.88),4326)::geography LIMIT 100;

def migrate(cr, version):
    """job_type_id (m2o) -> job_type_ids (m2m). The old column survives the
    upgrade (Odoo never drops columns), so copy it across, then drop it."""
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'service_ticket' AND column_name = 'job_type_id'
    """)
    if not cr.fetchone():
        return
    cr.execute("""
        INSERT INTO service_ticket_job_type_rel (ticket_id, job_type_id)
        SELECT id, job_type_id FROM service_ticket WHERE job_type_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    cr.execute("ALTER TABLE service_ticket DROP COLUMN job_type_id")

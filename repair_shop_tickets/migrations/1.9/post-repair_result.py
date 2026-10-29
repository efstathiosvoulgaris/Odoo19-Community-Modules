def migrate(cr, version):
    # Tickets resolved before 1.9 were all repairs: unrepaired ones were cancelled.
    cr.execute("""
        UPDATE service_ticket SET repair_result = 'repaired'
         WHERE state IN ('resolved', 'picked_up') AND repair_result IS NULL
    """)

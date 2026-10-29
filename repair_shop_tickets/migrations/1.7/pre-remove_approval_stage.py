def migrate(cr, version):
    """1.7 removes the estimate/approval stage: a ticket still waiting for approval goes back to
    «Νέο» before the selection value disappears."""
    cr.execute("UPDATE service_ticket SET state = 'new' WHERE state = 'waiting_approval'")

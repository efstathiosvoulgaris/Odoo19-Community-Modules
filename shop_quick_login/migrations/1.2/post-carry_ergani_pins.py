def migrate(cr, version):
    """1.2 gets its own PIN. Until now the quick login used the ERGANI PIN: carry each existing
    one over once, so nobody has to be given a new PIN on the day of the change."""
    cr.execute("""SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'hr_employee' AND column_name = 'ergani_pin_hash'""")
    if cr.fetchone():
        cr.execute("""UPDATE hr_employee SET ql_pin_hash = ergani_pin_hash
                      WHERE ql_pin_hash IS NULL AND ergani_pin_hash IS NOT NULL""")

from odoo import fields, models


class DiasRfCode(models.Model):
    """Κάθε κωδικός τιμολογίου που εκδόθηκε ποτέ. Μια πληρωμή βρίσκει το τιμολόγιό της με
    ακριβή αναζήτηση εδώ, όχι από τα id μέσα στον κωδικό: ένα παλιό τυπωμένο έντυπο ισχύει
    ακόμα κι αν το τιμολόγιο ξαναεπικυρώθηκε με άλλο ποσό."""
    _name = 'dias.rf.code'
    _description = 'ΔΙΑΣ: κωδικός RF που εκδόθηκε'
    _order = 'id desc'
    _rec_name = 'code'

    code = fields.Char('Κωδικός RF', required=True, index=True, readonly=True)
    company_id = fields.Many2one('res.company', required=True, readonly=True, index=True)
    move_id = fields.Many2one('account.move', 'Τιμολόγιο', readonly=True, index=True,
                              ondelete='cascade')
    partner_id = fields.Many2one('res.partner', 'Πελάτης', readonly=True)
    amount = fields.Monetary('Ποσό κωδικού', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')

    _code_company_uniq = models.Constraint(
        'unique(code, company_id)', 'Ο κωδικός RF υπάρχει ήδη.')

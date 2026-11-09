{
    'name': 'SKARLAS Website',
    'summary': 'Website design for eskarlas.gr',
    'category': 'Website',
    'version': '19.0.1.0.1',
    'author': 'eskarlas.gr',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/customizations.xml',
        'views/pages/home.xml',
        'views/pages/services.xml',
        'views/pages/digitalsignature.xml',
        'views/pages/contact.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            'skarlas_website/static/src/scss/primary_variables.scss',
        ],
        'web.assets_frontend': [
            'skarlas_website/static/src/scss/theme.scss',
        ],
    },
}

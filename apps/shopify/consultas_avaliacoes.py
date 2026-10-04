"""GraphQL das avaliacoes na Shopify: metaobject avaliacao_produto, arquivos e metafields.

Escopos do app: write_metaobject_definitions, write_metaobjects, write_files e
write_products.
"""

# "product_review" e reservado pela Shopify (definicao padrao do sistema).
TIPO = "avaliacao_produto"

DEFINICAO_POR_TIPO = """
query ($type: String!) { metaobjectDefinitionByType(type: $type) { id } }
"""

CRIAR_DEFINICAO = """
mutation ($definition: MetaobjectDefinitionCreateInput!) {
  metaobjectDefinitionCreate(definition: $definition) {
    metaobjectDefinition { id }
    userErrors { field message code }
  }
}
"""

UPSERT = """
mutation ($handle: MetaobjectHandleInput!, $metaobject: MetaobjectUpsertInput!) {
  metaobjectUpsert(handle: $handle, metaobject: $metaobject) {
    metaobject { id }
    userErrors { field message code }
  }
}
"""

EXCLUIR = """
mutation ($id: ID!) {
  metaobjectDelete(id: $id) { deletedId userErrors { field message code } }
}
"""

CRIAR_ARQUIVOS = """
mutation ($files: [FileCreateInput!]!) {
  fileCreate(files: $files) { files { id } userErrors { field message code } }
}
"""

EXCLUIR_ARQUIVOS = """
mutation ($fileIds: [ID!]!) {
  fileDelete(fileIds: $fileIds) { deletedFileIds userErrors { field message code } }
}
"""

DEFINICAO_METAFIELD = """
query ($namespace: String!, $key: String!) {
  metafieldDefinitions(first: 1, ownerType: PRODUCT, namespace: $namespace, key: $key) {
    nodes { id }
  }
}
"""

CRIAR_DEFINICAO_METAFIELD = """
mutation ($definition: MetafieldDefinitionInput!) {
  metafieldDefinitionCreate(definition: $definition) {
    createdDefinition { id }
    userErrors { field message code }
  }
}
"""

GRAVAR_METAFIELDS = """
mutation ($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { key }
    userErrors { field message code }
  }
}
"""

APAGAR_METAFIELDS = """
mutation ($metafields: [MetafieldIdentifierInput!]!) {
  metafieldsDelete(metafields: $metafields) {
    deletedMetafields { key }
    userErrors { field message }
  }
}
"""

# O tema le daqui (Liquid): product.metafields.custom.reviews.value etc.
CAMPOS_DEFINICAO = [
    {"key": "product", "name": "Produto", "type": "product_reference"},
    {"key": "author", "name": "Nome", "type": "single_line_text_field"},
    {"key": "rating", "name": "Nota", "type": "number_integer",
     "validations": [{"name": "min", "value": "1"}, {"name": "max", "value": "5"}]},
    {"key": "body", "name": "Comentario", "type": "multi_line_text_field"},
    {"key": "photos", "name": "Fotos", "type": "list.file_reference"},
    {"key": "verified", "name": "Compra verificada", "type": "boolean"},
    {"key": "date", "name": "Data", "type": "date"},
]


def definicao():
    return {
        "type": TIPO, "name": "Avaliacao de produto", "displayNameKey": "author",
        "access": {"storefront": "PUBLIC_READ"},
        "capabilities": {"publishable": {"enabled": True}},
        "fieldDefinitions": CAMPOS_DEFINICAO,
    }


SUBIR_ARQUIVO = """
mutation ($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}
"""

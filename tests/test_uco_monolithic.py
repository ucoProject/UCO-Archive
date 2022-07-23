#!/usr/bin/env python3

# This software was developed at the National Institute of Standards
# and Technology by employees of the Federal Government in the course
# of their official duties. Pursuant to title 17 Section 105 of the
# United States Code this software is not subject to copyright
# protection and is in the public domain. NIST assumes no
# responsibility whatsoever for its use by other parties, and makes
# no guarantees, expressed or implied, about its quality,
# reliability, or any other characteristic.
#
# We would appreciate acknowledgement if the software is used.

import logging
import os
from typing import Generator, List, Optional, Set, Tuple, Union

import pytest
import rdflib.plugins.sparql.processor
from rdflib import BNode, Graph, Literal, RDF, URIRef
from rdflib.term import Node

IdentifiedNode = Union[BNode, URIRef]


@pytest.fixture(scope="module")
def graph() -> Generator[Graph, None, None]:
    graph = Graph()
    graph.parse(os.path.join(os.path.dirname(__file__), "uco_monolithic.ttl"))
    assert len(graph) > 0, "Failed to load uco_monolithic.ttl."
    yield graph


def test_max_1_sh_datatype_per_property_shape(graph: Graph) -> None:
    """
    This enforces the maximum sh:datatype count of 1, as specified here:

    "A shape has at most one value for sh:datatype."
    https://www.w3.org/TR/shacl/#DatatypeConstraintComponent

    This is encoded in the SHACL ontology with the statement 'sh:DatatypeConstraintComponent-datatype sh:maxCount 1 .'
    """
    expected: Set[Tuple[URIRef, URIRef, Literal]] = set()  # This set is intentionally empty.
    computed: Set[Tuple[URIRef, URIRef, Literal]] = set()

    nsdict = {
      "sh": rdflib.SH
    }

    query_object = rdflib.plugins.sparql.processor.prepareQuery("""\
SELECT ?nClass ?nPath ?lConstraintDatatypeTally
WHERE {
  {
    SELECT ?nClass ?nPath (COUNT(DISTINCT ?nConstraintDatatype) AS ?lConstraintDatatypeTally)
    WHERE {
      ?nClass
        sh:property ?nPropertyShape ;
        .

      ?nPropertyShape
        sh:datatype ?nConstraintDatatype ;
        sh:path ?nPath ;
        .
    } GROUP BY ?nClass ?nPath
  }

  FILTER (?lConstraintDatatypeTally > 1)
}
""", initNs=nsdict)  # type: ignore
    for result in graph.query(query_object):
        computed.add(result)
    assert expected == computed


def rdf_list_to_member_list(graph: Graph, n_list: IdentifiedNode) -> List[Node]:
    """
    Recursive convert RDF list to Python Node list, from tail-back.
    """
    default_retval: List[Node] = []
    if n_list == RDF.nil:
        return default_retval

    n_first: Optional[Node] = None
    n_rest: Optional[IdentifiedNode] = None

    for triple0 in graph.triples((n_list, RDF.first, None)):
        n_first = triple0[2]
    if n_first is None:
        return default_retval

    for triple1 in graph.triples((n_list, RDF.rest, None)):
        assert isinstance(triple1[2], (BNode, URIRef))
        n_rest = triple1[2]
    assert n_rest is not None

    rest_of_list = rdf_list_to_member_list(graph, n_rest)
    rest_of_list.insert(0, n_first)
    return rest_of_list


def test_semi_open_vocabulary_owl_shacl_alignment(graph: Graph) -> None:
    """
    This test enforces that when a DatatypeProperty following the "Semi-open vocabulary" design of UCO 0.8.0 is used, that its SHACL shape's enumerant list matches the rdfs:Datatype's enumerant list.
    """
    # A member of these sets is a class's IRI, its semi-open vocabulary's IRI, the list in the SHACL shape, and the list in the Datatype.
    # (The type of the lists is a Tuple because a Set in Python cannot contain a List.)
    # The expected set intentionally has length 0.
    expected: Set[Tuple[URIRef, URIRef, Tuple[Node, ...], Tuple[Node, ...]]] = set()
    computed: Set[Tuple[URIRef, URIRef, Tuple[Node, ...], Tuple[Node, ...]]] = set()

    query = """
SELECT ?nClass ?nDatatype ?nShaclList ?nRdfsList
WHERE {
  ?nClass
    sh:property / sh:or / rdf:rest* / rdf:first ?nMemberCheckShape ;
    .
  ?nMemberCheckShape
    sh:datatype ?nDatatype ;
    sh:in ?nShaclList ;
    .
  ?nDatatype
    a rdfs:Datatype ;
    owl:oneOf ?nRdfsList ;
    .
}
"""
    result_tally = 0
    test_cases: Set[Tuple[URIRef, URIRef, IdentifiedNode, IdentifiedNode]] = set()
    for (result_no, result) in enumerate(graph.query(query)):
        result_tally = result_no + 1
        assert isinstance(result[0], URIRef)
        assert isinstance(result[1], URIRef)
        if isinstance(result[2], URIRef) and isinstance(result[3], URIRef):
            assert result[2] == result[3]
        else:
            assert isinstance(result[2], (BNode, URIRef))
            assert isinstance(result[3], (BNode, URIRef))
        test_cases.add(result)
    assert result_tally > 0, "Pattern for semi-open vocabularies is no longer aligned with test."

    for test_case in test_cases:
        n_shacl_list = test_case[2]
        n_rdfs_list = test_case[3]

        if n_shacl_list is n_rdfs_list:
            # No point in doing any comparison work.
            continue

        shacl_list = rdf_list_to_member_list(graph, n_shacl_list)
        rdfs_list = rdf_list_to_member_list(graph, n_rdfs_list)
        if rdfs_list == shacl_list:
            logging.debug("Match")
        else:
            logging.debug(n_shacl_list)
            logging.debug(n_rdfs_list)
            shacl_tuple = tuple(shacl_list)
            rdfs_tuple = tuple(rdfs_list)
            computed.add((test_case[0], test_case[1], shacl_tuple, rdfs_tuple))

    assert expected == computed

import strawberry

@strawberry.input
class GraphPaginationInput:
    limit: int | None = 200
    offset: int | None = 0

@strawberry.input
class TablePaginationInput:
    limit: int | None = 200
    offset: int | None = 0
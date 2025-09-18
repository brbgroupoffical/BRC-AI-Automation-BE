from rest_framework.pagination import PageNumberPagination


class TenResultsSetPagination(PageNumberPagination):
    page_size = 10                      # Always return 10 results per page
    page_size_query_param = None        # Prevent client overriding
    max_page_size = 10                  # Hard limit

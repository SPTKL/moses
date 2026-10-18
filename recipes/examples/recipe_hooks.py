"""Example trusted extensions; review and install your own module in real use."""
import pyarrow as pa


def records(count):
    for index in range(count):
        yield {'id': f'{index:03d}', 'amount': index + 1}


def multiply_amount(table, factor):
    amounts = [value * factor for value in table['amount'].to_pylist()]
    return table.set_column(table.column_names.index('amount'), 'amount', pa.array(amounts, type=pa.int64()))

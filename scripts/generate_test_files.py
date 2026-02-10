"""Generate test Power BI files for Semantic Model Explorer testing.

Creates:
- .pbit file (ZIP with DataModelSchema as UTF-16LE JSON)
- .bim file (standalone JSON)
- .tmdl folder (PBIP developer format)
- .zip of TMDL folder
"""

import json
import os
import zipfile
import io


def make_test_model():
    """Create a test semantic model as a BIM/TMSL JSON structure."""
    return {
        "name": "Test Sales Model",
        "compatibilityLevel": 1604,
        "model": {
            "culture": "en-US",
            "tables": [
                {
                    "name": "Sales",
                    "columns": [
                        {"name": "OrderID", "dataType": "int64", "sourceColumn": "OrderID"},
                        {"name": "OrderDate", "dataType": "dateTime", "sourceColumn": "OrderDate", "formatString": "d/m/yyyy"},
                        {"name": "Amount", "dataType": "decimal", "sourceColumn": "Amount", "formatString": "$#,##0"},
                        {"name": "CustomerKey", "dataType": "int64", "sourceColumn": "CustomerKey", "isHidden": True},
                        {"name": "ProductKey", "dataType": "int64", "sourceColumn": "ProductKey", "isHidden": True},
                        {
                            "name": "Margin",
                            "dataType": "decimal",
                            "type": "calculated",
                            "expression": "Sales[Amount] - Sales[Cost]",
                            "formatString": "$#,##0",
                        },
                        {"name": "Cost", "dataType": "decimal", "sourceColumn": "Cost", "isHidden": True},
                    ],
                    "measures": [
                        {
                            "name": "Total Sales",
                            "expression": "SUM(Sales[Amount])",
                            "formatString": "$#,##0",
                            "displayFolder": "Revenue",
                            "description": "Total revenue from all transactions",
                        },
                        {
                            "name": "YoY Growth",
                            "expression": "VAR CurrentYear = [Total Sales]\nVAR PriorYear = CALCULATE([Total Sales], SAMEPERIODLASTYEAR('Date'[Date]))\nRETURN DIVIDE(CurrentYear - PriorYear, PriorYear)",
                            "formatString": "0.0%",
                            "displayFolder": "Revenue",
                        },
                        {
                            "name": "Order Count",
                            "expression": "COUNTROWS(Sales)",
                            "formatString": "#,##0",
                            "displayFolder": "Counts",
                        },
                        {
                            "name": "Avg Order Value",
                            "expression": "DIVIDE([Total Sales], [Order Count])",
                            "formatString": "$#,##0.00",
                            "displayFolder": "Revenue",
                        },
                        {
                            "name": "Total Cost",
                            "expression": "SUM(Sales[Cost])",
                            "formatString": "$#,##0",
                            "isHidden": True,
                        },
                        {
                            "name": "Margin %",
                            "expression": "DIVIDE([Total Sales] - [Total Cost], [Total Sales])",
                            "formatString": "0.0%",
                            "displayFolder": "Profitability",
                        },
                    ],
                    "partitions": [
                        {
                            "name": "Sales",
                            "source": {
                                "type": "m",
                                "expression": 'let\n    Source = Sql.Database("server", "db"),\n    Sales = Source{[Schema="dbo",Item="Sales"]}[Data]\nin\n    Sales',
                            },
                        }
                    ],
                },
                {
                    "name": "Date",
                    "columns": [
                        {"name": "Date", "dataType": "dateTime", "sourceColumn": "Date", "formatString": "d/m/yyyy"},
                        {"name": "Year", "dataType": "int64", "sourceColumn": "Year"},
                        {"name": "Quarter", "dataType": "string", "sourceColumn": "Quarter"},
                        {"name": "Month", "dataType": "string", "sourceColumn": "Month", "sortByColumn": "MonthNumber"},
                        {"name": "MonthNumber", "dataType": "int64", "sourceColumn": "MonthNumber", "isHidden": True},
                    ],
                    "measures": [
                        {
                            "name": "Current Year",
                            "expression": "YEAR(TODAY())",
                            "formatString": "0",
                        },
                    ],
                    "hierarchies": [
                        {
                            "name": "Date Hierarchy",
                            "levels": [
                                {"name": "Year", "column": "Year"},
                                {"name": "Quarter", "column": "Quarter"},
                                {"name": "Month", "column": "Month"},
                            ],
                        }
                    ],
                    "partitions": [
                        {
                            "name": "Date",
                            "source": {
                                "type": "m",
                                "expression": 'let\n    Source = List.Dates(#date(2020,1,1), 1461, #duration(1,0,0,0)),\n    Table = Table.FromList(Source)\nin\n    Table',
                            },
                        }
                    ],
                },
                {
                    "name": "Product",
                    "columns": [
                        {"name": "ProductKey", "dataType": "int64", "sourceColumn": "ProductKey"},
                        {"name": "Product Name", "dataType": "string", "sourceColumn": "ProductName"},
                        {"name": "Category", "dataType": "string", "sourceColumn": "Category"},
                        {"name": "Subcategory", "dataType": "string", "sourceColumn": "Subcategory"},
                        {"name": "Unit Price", "dataType": "decimal", "sourceColumn": "UnitPrice", "formatString": "$#,##0.00"},
                    ],
                    "hierarchies": [
                        {
                            "name": "Product Hierarchy",
                            "levels": [
                                {"name": "Category", "column": "Category"},
                                {"name": "Subcategory", "column": "Subcategory"},
                                {"name": "Product Name", "column": "Product Name"},
                            ],
                        }
                    ],
                    "partitions": [{"name": "Product", "source": {"type": "m", "expression": "Source"}}],
                },
                {
                    "name": "Customer",
                    "columns": [
                        {"name": "CustomerKey", "dataType": "int64", "sourceColumn": "CustomerKey"},
                        {"name": "Customer Name", "dataType": "string", "sourceColumn": "CustomerName"},
                        {"name": "Region", "dataType": "string", "sourceColumn": "Region"},
                        {"name": "Country", "dataType": "string", "sourceColumn": "Country"},
                    ],
                    "partitions": [{"name": "Customer", "source": {"type": "m", "expression": "Source"}}],
                },
                {
                    "name": "Hidden Helper",
                    "isHidden": True,
                    "columns": [
                        {"name": "ID", "dataType": "int64", "sourceColumn": "ID"},
                        {"name": "Value", "dataType": "string", "sourceColumn": "Value"},
                    ],
                    "partitions": [{"name": "HiddenHelper", "source": {"type": "m", "expression": "Source"}}],
                },
            ],
            "relationships": [
                {
                    "name": "Sales_Product",
                    "fromTable": "Sales",
                    "fromColumn": "ProductKey",
                    "toTable": "Product",
                    "toColumn": "ProductKey",
                    "fromCardinality": "many",
                    "toCardinality": "one",
                },
                {
                    "name": "Sales_Customer",
                    "fromTable": "Sales",
                    "fromColumn": "CustomerKey",
                    "toTable": "Customer",
                    "toColumn": "CustomerKey",
                    "fromCardinality": "many",
                    "toCardinality": "one",
                },
                {
                    "name": "Sales_Date",
                    "fromTable": "Sales",
                    "fromColumn": "OrderDate",
                    "toTable": "Date",
                    "toColumn": "Date",
                    "fromCardinality": "many",
                    "toCardinality": "one",
                },
                {
                    "name": "Sales_Date_Inactive",
                    "fromTable": "Sales",
                    "fromColumn": "OrderDate",
                    "toTable": "Date",
                    "toColumn": "Date",
                    "isActive": False,
                    "fromCardinality": "many",
                    "toCardinality": "one",
                    "crossFilteringBehavior": "bothDirections",
                },
            ],
            "roles": [
                {
                    "name": "Regional Manager",
                    "tablePermissions": [
                        {
                            "name": "Customer",
                            "filterExpression": "[Region] = USERPRINCIPALNAME()",
                        }
                    ],
                },
                {
                    "name": "Executive",
                    "tablePermissions": [{"name": "Sales"}],
                },
            ],
        },
    }


def generate_bim(output_dir):
    """Generate a .bim file."""
    model = make_test_model()
    path = os.path.join(output_dir, "test-model.bim")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)
    print(f"Generated {path} ({os.path.getsize(path)} bytes)")
    return path


def generate_pbit(output_dir):
    """Generate a .pbit file (ZIP containing DataModelSchema as UTF-16LE)."""
    model = make_test_model()
    json_str = json.dumps(model, indent=2)
    utf16_bytes = ("\ufeff" + json_str).encode("utf-16-le")

    path = os.path.join(output_dir, "test-model.pbit")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("DataModelSchema", utf16_bytes)
        zf.writestr("Version", "2.0")
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/></Types>',
        )
    print(f"Generated {path} ({os.path.getsize(path)} bytes)")
    return path


def generate_tmdl(output_dir):
    """Generate TMDL folder structure."""
    tmdl_dir = os.path.join(output_dir, "tmdl-test-model", "definition")
    tables_dir = os.path.join(tmdl_dir, "tables")
    os.makedirs(tables_dir, exist_ok=True)

    # database.tmdl
    with open(os.path.join(tmdl_dir, "database.tmdl"), "w") as f:
        f.write("compatibilityLevel: 1604\n")

    # model.tmdl
    with open(os.path.join(tmdl_dir, "model.tmdl"), "w") as f:
        f.write(
            """model Model
\tculture: en-US
\tdefaultPowerBIDataSourceVersion: powerBI_V3

ref table Sales
ref table Date
ref table Product
ref table Customer
ref table 'Hidden Helper'

ref role 'Regional Manager'
ref role Executive
"""
        )

    # relationships.tmdl
    with open(os.path.join(tmdl_dir, "relationships.tmdl"), "w") as f:
        f.write(
            """relationship Sales_Product
\tfromColumn: Sales.ProductKey
\ttoColumn: Product.ProductKey

relationship Sales_Customer
\tfromColumn: Sales.CustomerKey
\ttoColumn: Customer.CustomerKey

relationship Sales_Date
\tfromColumn: Sales.OrderDate
\ttoColumn: Date.Date

relationship Sales_Date_Inactive
\tisActive: false
\tcrossFilteringBehavior: bothDirections
\tfromColumn: Sales.OrderDate
\ttoColumn: Date.Date

relationship Dotted_Table_Rel
\tfromColumn: 'Schema.Sales'.ProductKey
\ttoColumn: 'Schema.Product'.ProductKey
"""
        )

    # tables/Sales.tmdl
    with open(os.path.join(tables_dir, "Sales.tmdl"), "w") as f:
        f.write(
            """table Sales
\tlineageTag: test-sales-001

\tmeasure 'Total Sales' = SUM(Sales[Amount])
\t\tformatString: $#,##0
\t\tdisplayFolder: Revenue
\t\tdescription: Total revenue from all transactions

\tmeasure 'YoY Growth' =
\t\t\tVAR CurrentYear = [Total Sales]
\t\t\tVAR PriorYear = CALCULATE([Total Sales], SAMEPERIODLASTYEAR('Date'[Date]))
\t\t\tRETURN DIVIDE(CurrentYear - PriorYear, PriorYear)
\t\tformatString: 0.0%
\t\tdisplayFolder: Revenue

\tmeasure 'Order Count' = COUNTROWS(Sales)
\t\tformatString: #,##0
\t\tdisplayFolder: Counts

\tmeasure 'Avg Order Value' = DIVIDE([Total Sales], [Order Count])
\t\tformatString: $#,##0.00
\t\tdisplayFolder: Revenue

\tmeasure 'Total Cost' = SUM(Sales[Cost])
\t\tformatString: $#,##0
\t\tisHidden

\tmeasure 'Margin %' = DIVIDE([Total Sales] - [Total Cost], [Total Sales])
\t\tformatString: 0.0%
\t\tdisplayFolder: Profitability

\tcolumn OrderID
\t\tdataType: int64
\t\tsourceColumn: OrderID

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: d/m/yyyy
\t\tsourceColumn: OrderDate

\tcolumn Amount
\t\tdataType: decimal
\t\tformatString: $#,##0
\t\tsourceColumn: Amount

\tcolumn CustomerKey
\t\tdataType: int64
\t\tisHidden
\t\tsourceColumn: CustomerKey

\tcolumn ProductKey
\t\tdataType: int64
\t\tisHidden
\t\tsourceColumn: ProductKey

\tcolumn Margin
\t\tdataType: decimal
\t\tformatString: $#,##0
\t\texpression = Sales[Amount] - Sales[Cost]

\tcolumn Cost
\t\tdataType: decimal
\t\tisHidden
\t\tsourceColumn: Cost

\tpartition Sales = m
\t\tmode: import
\t\tsource =
\t\t\tlet
\t\t\t    Source = Sql.Database("server", "db"),
\t\t\t    Sales = Source{[Schema="dbo",Item="Sales"]}[Data]
\t\t\tin
\t\t\t    Sales
"""
        )

    # tables/Date.tmdl
    with open(os.path.join(tables_dir, "Date.tmdl"), "w") as f:
        f.write(
            """table Date
\tlineageTag: test-date-001

\tmeasure 'Current Year' = YEAR(TODAY())
\t\tformatString: 0

\tcolumn Date
\t\tdataType: dateTime
\t\tformatString: d/m/yyyy
\t\tsourceColumn: Date

\tcolumn Year
\t\tdataType: int64
\t\tsourceColumn: Year

\tcolumn Quarter
\t\tdataType: string
\t\tsourceColumn: Quarter

\tcolumn Month
\t\tdataType: string
\t\tsourceColumn: Month
\t\tsortByColumn: MonthNumber

\tcolumn MonthNumber
\t\tdataType: int64
\t\tisHidden
\t\tsourceColumn: MonthNumber

\thierarchy 'Date Hierarchy'
\t\tlevel Year
\t\tlevel Quarter
\t\tlevel Month

\tpartition Date = m
\t\tmode: import
\t\tsource =
\t\t\tlet
\t\t\t    Source = List.Dates(#date(2020,1,1), 1461, #duration(1,0,0,0)),
\t\t\t    Table = Table.FromList(Source)
\t\t\tin
\t\t\t    Table
"""
        )

    # tables/Product.tmdl
    with open(os.path.join(tables_dir, "Product.tmdl"), "w") as f:
        f.write(
            """table Product
\tlineageTag: test-product-001

\tcolumn ProductKey
\t\tdataType: int64
\t\tsourceColumn: ProductKey

\tcolumn 'Product Name'
\t\tdataType: string
\t\tsourceColumn: ProductName

\tcolumn Category
\t\tdataType: string
\t\tsourceColumn: Category

\tcolumn Subcategory
\t\tdataType: string
\t\tsourceColumn: Subcategory

\tcolumn 'Unit Price'
\t\tdataType: decimal
\t\tformatString: $#,##0.00
\t\tsourceColumn: UnitPrice

\thierarchy 'Product Hierarchy'
\t\tlevel Category
\t\tlevel Subcategory
\t\tlevel 'Product Name'

\tpartition Product = m
\t\tmode: import
\t\tsource = Source
"""
        )

    # tables/Customer.tmdl
    with open(os.path.join(tables_dir, "Customer.tmdl"), "w") as f:
        f.write(
            """table Customer
\tlineageTag: test-customer-001

\tcolumn CustomerKey
\t\tdataType: int64
\t\tsourceColumn: CustomerKey

\tcolumn 'Customer Name'
\t\tdataType: string
\t\tsourceColumn: CustomerName

\tcolumn Region
\t\tdataType: string
\t\tsourceColumn: Region

\tcolumn Country
\t\tdataType: string
\t\tsourceColumn: Country

\tpartition Customer = m
\t\tmode: import
\t\tsource = Source
"""
        )

    # tables/Hidden Helper.tmdl
    with open(os.path.join(tables_dir, "Hidden Helper.tmdl"), "w") as f:
        f.write(
            """table 'Hidden Helper'
\tisHidden
\tlineageTag: test-hidden-001

\tcolumn ID
\t\tdataType: int64
\t\tsourceColumn: ID

\tcolumn Value
\t\tdataType: string
\t\tsourceColumn: Value

\tpartition HiddenHelper = m
\t\tmode: import
\t\tsource = Source
"""
        )

    print(f"Generated TMDL folder at {tmdl_dir}")

    # Also create a ZIP of the TMDL folder
    zip_path = os.path.join(output_dir, "tmdl-test-model.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(os.path.join(output_dir, "tmdl-test-model")):
            for file in files:
                abs_path = os.path.join(root, file)
                arc_path = os.path.relpath(abs_path, output_dir)
                zf.write(abs_path, arc_path)
    print(f"Generated {zip_path} ({os.path.getsize(zip_path)} bytes)")
    return tmdl_dir, zip_path


def generate_edge_case_files(output_dir):
    """Generate edge case test files for comprehensive testing."""

    # 1. Empty model (no tables)
    empty_model = {
        "name": "Empty Model",
        "compatibilityLevel": 1604,
        "model": {"tables": []},
    }
    path = os.path.join(output_dir, "edge-empty-model.bim")
    with open(path, "w") as f:
        json.dump(empty_model, f)
    print(f"Generated {path}")

    # 2. Model with special characters in names
    special_model = {
        "name": "Special <Characters> & \"Quotes\"",
        "compatibilityLevel": 1604,
        "model": {
            "tables": [
                {
                    "name": "Table with Spaces & Symbols!",
                    "columns": [
                        {"name": "Column <html>", "dataType": "string", "sourceColumn": "x"},
                        {"name": "Column \"quoted\"", "dataType": "int64", "sourceColumn": "y"},
                        {"name": "Col|pipe|bar", "dataType": "string", "sourceColumn": "z"},
                        {"name": "Col:colon:name", "dataType": "string", "sourceColumn": "w"},
                        {"name": "Unicode\u00e9\u00e8\u00fc\u00f1", "dataType": "string", "sourceColumn": "u"},
                    ],
                    "measures": [
                        {
                            "name": "Measure with <script>alert(1)</script>",
                            "expression": "1+1",
                        },
                        {
                            "name": "Backtick`measure`",
                            "expression": 'CALCULATE([Total], FILTER(\'Table with Spaces & Symbols!\'[Column <html>], TRUE()))',
                        },
                    ],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                },
                {
                    "name": "Normal Table",
                    "columns": [
                        {"name": "ID", "dataType": "int64", "sourceColumn": "ID"},
                    ],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                },
            ],
            "relationships": [
                {
                    "name": "r1",
                    "fromTable": "Table with Spaces & Symbols!",
                    "fromColumn": "Column <html>",
                    "toTable": "Normal Table",
                    "toColumn": "ID",
                },
            ],
        },
    }
    path = os.path.join(output_dir, "edge-special-chars.bim")
    with open(path, "w") as f:
        json.dump(special_model, f)
    print(f"Generated {path}")

    # 3. Model with no measures
    no_measures = {
        "name": "No Measures Model",
        "compatibilityLevel": 1604,
        "model": {
            "tables": [
                {
                    "name": "Data",
                    "columns": [
                        {"name": "ID", "dataType": "int64", "sourceColumn": "ID"},
                        {"name": "Name", "dataType": "string", "sourceColumn": "Name"},
                    ],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                },
            ],
        },
    }
    path = os.path.join(output_dir, "edge-no-measures.bim")
    with open(path, "w") as f:
        json.dump(no_measures, f)
    print(f"Generated {path}")

    # 4. Model with only hidden items
    hidden_model = {
        "name": "All Hidden",
        "compatibilityLevel": 1604,
        "model": {
            "tables": [
                {
                    "name": "HiddenTable",
                    "isHidden": True,
                    "columns": [
                        {"name": "HiddenCol", "dataType": "int64", "sourceColumn": "x", "isHidden": True},
                    ],
                    "measures": [
                        {"name": "HiddenMeasure", "expression": "1", "isHidden": True},
                    ],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                },
            ],
        },
    }
    path = os.path.join(output_dir, "edge-all-hidden.bim")
    with open(path, "w") as f:
        json.dump(hidden_model, f)
    print(f"Generated {path}")

    # 5. Single-table model (no relationships)
    single = {
        "name": "Single Table",
        "compatibilityLevel": 1604,
        "model": {
            "tables": [
                {
                    "name": "OnlyTable",
                    "columns": [{"name": "Val", "dataType": "string", "sourceColumn": "Val"}],
                    "measures": [{"name": "Count", "expression": "COUNTROWS(OnlyTable)"}],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                },
            ],
        },
    }
    path = os.path.join(output_dir, "edge-single-table.bim")
    with open(path, "w") as f:
        json.dump(single_model, f) if False else json.dump(single, f)
    print(f"Generated {path}")

    # 6. Very long names
    long_model = {
        "name": "Long" * 50,
        "compatibilityLevel": 1604,
        "model": {
            "tables": [
                {
                    "name": "T" * 200,
                    "columns": [
                        {"name": "C" * 200, "dataType": "string", "sourceColumn": "x"},
                    ],
                    "measures": [
                        {"name": "M" * 200, "expression": "SUM(" + "T" * 200 + "[" + "C" * 200 + "])"},
                    ],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                },
            ],
        },
    }
    path = os.path.join(output_dir, "edge-long-names.bim")
    with open(path, "w") as f:
        json.dump(long_model, f)
    print(f"Generated {path}")

    # 7. Many tables (wide model)
    many_tables = {
        "name": "Wide Model",
        "compatibilityLevel": 1604,
        "model": {
            "tables": [
                {
                    "name": f"Table_{i:03d}",
                    "columns": [
                        {"name": f"Col_{j}", "dataType": "string", "sourceColumn": f"col{j}"}
                        for j in range(5)
                    ],
                    "measures": [{"name": f"M_{i}", "expression": f"COUNTROWS(Table_{i:03d})"}],
                    "partitions": [{"name": "p", "source": {"type": "m", "expression": "Source"}}],
                }
                for i in range(30)
            ],
            "relationships": [
                {
                    "name": f"r_{i}",
                    "fromTable": f"Table_{i+1:03d}",
                    "fromColumn": "Col_0",
                    "toTable": f"Table_{i:03d}",
                    "toColumn": "Col_0",
                }
                for i in range(29)
            ],
        },
    }
    path = os.path.join(output_dir, "edge-many-tables.bim")
    with open(path, "w") as f:
        json.dump(many_tables, f)
    print(f"Generated {path}")


if __name__ == "__main__":
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "test-files")
    os.makedirs(output_dir, exist_ok=True)

    generate_bim(output_dir)
    generate_pbit(output_dir)
    generate_tmdl(output_dir)
    generate_edge_case_files(output_dir)
    print("\nAll test files generated successfully!")

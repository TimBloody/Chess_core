# PGN output

Сохранённые из приложения партии и анализы создаются здесь как UTF-8 PGN.
Метаданные хранятся внутри файла в стандартных PGN-тегах, которые читает
ChessBase (`Event`, `Site`, `Date`, `Round`, `White`, `Black`, `Result`,
`WhiteElo`, `BlackElo`, `ECO`, `Opening`, `Variation`, `Annotator`).

Чтобы объединить все PGN текущей директории в одну открываемую ChessBase базу:

```powershell
python -m chess_core.tools.pgn_database
```

Или из корня проекта:

```powershell
.\.venv\Scripts\python.exe -m chess_core.tools.pgn_database output -o output\database.pgn
```

ChessBase откроет `database.pgn` и при необходимости сможет импортировать её в
собственный проприетарный формат базы.

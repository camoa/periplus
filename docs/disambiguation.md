# One word, several things

In many code bases one word names several things. "Account" can be the login of a person and also
the billing record of a customer. This page shows how to tell such things apart with the map, and
how to save the answer so that the next person and the next AI session do not mix them up again.

The work has six steps: find the word, see its meanings, check each in the code, ask a person
where the code cannot say, save the answer as descriptions, and write down the words as terms. An AI agent with the periplus
skills does the same steps. You can ask it in plain words:

```
This project has a Periplus map. "Account" seems to mean two things here. Find each one, tell me
how they differ, and ask me where the code cannot say.
```

The example below is a small invented PHP project, mapped with the bundled `php_basic` rutter. It
has two classes named `Account`: `Acme\User\Account` and `Acme\Billing\Account`.

## 1. Find the word

`periplus find` lists every thing whose id, attributes or description holds the word. Each row
gives the thing's type and its place.

```
$ periplus find account --type php.class --no-edges
periplus find: 2 things (2 main), 0 edges
main by type: php.class 2

php.type::Acme\\Billing\\Account  php.class  mapped  src/Billing/Account.php:5
      | class Account
php.type::Acme\\User\\Account  php.class  mapped  src/User/Account.php:5
      | class Account
```

`--type` keeps one type. Without it, the search lists 13 things and 13 links.

A short name that fits several main things is refused, and Periplus does not pick one.
`periplus show Account` exits with code 31 and lists the 6 ids it fits. A longer name can fit one
main thing and some parts, because other ids end in the same text. Then the main thing is meant.
Here a parameter type ends in the class name, and `show` takes the class:

```
$ periplus show 'Acme\Billing\Account'
periplus show php.type::Acme\\Billing\\Account
type: php.class
state: mapped
location: src/Billing/Account.php:5
...
warning: resolved 'Acme\\Billing\\Account' to php.type::Acme\\Billing\\Account
```

Give the full id, such as `php.type::Acme\Billing\Account`, with single backslashes.

## 2. See its meanings

The map tells the two apart in two ways.

- **By structure.** Each thing found in the code has its own id, type, file and line. The ids show two namespaces,
  `User` and `Billing`.
- **By its links.** What uses each thing shows the part of the code it belongs to. Ask the map
  what sets off each class's method:

```
$ periplus affected 'php.method::Acme\User\Account::changePassword'
Account::changePassword  php.method  mapped  start  src/User/Account.php:7
  resetPassword  php.method  mapped  calls (rev)  src/Auth/LoginController.php:11

$ periplus affected 'php.method::Acme\Billing\Account::balance'
Account::balance  php.method  mapped  start  src/Billing/Account.php:7
  build  php.method  mapped  calls (rev)  src/Invoice/StatementBuilder.php:11
```

The first account takes part in login. The second takes part in invoices.

## 3. Check each in the code

The map says where to read. The code says what each thing does. `periplus show` on each id lists
its links and the place of each, so you know which lines to open.

```
$ periplus show 'php.type::Acme\Billing\Account'
type: php.class
state: mapped
location: src/Billing/Account.php:5
...

Outgoing (1):
  contains:
    php.method::Acme\\Billing\\Account::balance  php.method  mapped  src/Billing/Account.php:7  ...
```

Here the code shows that the user account changes a password hash, and that the billing account
returns an open invoice total.

## 4. Ask a person where the code cannot say

Some meaning is not in the code. Nothing in `Acme\Billing\Account` says whether the customer is a
company or one person. Ask someone who knows the business, and write down the answer. In this
example the answer is a customer organisation.

An agent that follows the skills says which thing it means before it goes on, and asks you when
the map and the code cannot tell.

## 5. Save the answer as descriptions

Write one entry for each thing in `.periplus/descriptions.yaml`. Where a thing shares its name
with another, the entry uses the words that set this thing apart, and does not name the other
meaning. The periplus-describe skill gives the rules and the file format.

```yaml
nodes:
  php.type::Acme\Billing\Account:
    text: The billing account of a customer organisation, with the total of its open invoices.
    file: src/Billing/Account.php
    line: 5
  php.type::Acme\User\Account:
    text: The sign-in account of one person, with the password they log in with.
    file: src/User/Account.php
    line: 5
```

Then run `periplus stamp`. It writes into each entry a fingerprint of the code it describes, so
`periplus stale` lists the entry when that code changes.

Before the descriptions, `periplus find customer` printed `no matches`. Now plain words reach the
right thing, and each row prints its description after `#`:

```
$ periplus find customer
periplus find: 1 thing (1 main), 0 edges
main by type: php.class 1

php.type::Acme\\Billing\\Account  php.class  mapped  src/Billing/Account.php:5  [description]
      | class Account
      # The billing account of a customer organisation, with the total of its open invoices.
```

Do not write what a thing is not. `periplus find` matches every word of a description, so a user
account entry that ended "Not the billing account of a customer organisation" made `periplus find
customer` return both classes.

## 6. Write down the words as terms

A description says what one thing does. A term says what a word of the project means, and names
the things it covers. Write a term when one word names two things, when people use a word the
code does not hold, or when an old name is still in use. Terms go under `terms:` in the same
`.periplus/descriptions.yaml`. In this example, people once said "client" for the customer:

```yaml
terms:
  customer:
    text: The organisation that is invoiced and pays.
    words: [customer, account, billing account]
    old: [client]
    ids: ['php.type::Acme\Billing\Account']
    origin: person
  user-account:
    text: How one person signs in, with a password.
    words: [account, user account, login]
    ids: ['php.type::Acme\User\Account']
    origin: code
```

Two terms hold the word "account", so it has two meanings. `periplus find` prints each one before
the rows, and marks each row with its term:

```
$ periplus find account --type php.class --no-edges
periplus find: 2 things (2 main), 0 edges
main by type: php.class 2
terms matching the words: 2
  customer: The organisation that is invoiced and pays.
    word: account; origin: person; ids: php.type::Acme\\Billing\\Account
  user-account: How one person signs in, with a password.
    word: account; origin: code; ids: php.type::Acme\\User\\Account
  'account' has 2 meanings: customer, user-account

php.type::Acme\\Billing\\Account  php.class  mapped  src/Billing/Account.php:5  [term customer]
      | class Account
      # The billing account of a customer organisation, with the total of its open invoices.
php.type::Acme\\User\\Account  php.class  mapped  src/User/Account.php:5  [term user-account]
      | class Account
      # The sign-in account of one person, with the password they log in with.
```

An old name reaches the thing too, though no id or description holds it:

```
$ periplus find client --no-edges
periplus find: 1 thing (1 main), 0 edges
main by type: php.class 1
terms matching the words: 1
  customer: The organisation that is invoiced and pays.
    old name: client; origin: person; ids: php.type::Acme\\Billing\\Account

php.type::Acme\\Billing\\Account  php.class  mapped  src/Billing/Account.php:5  [term customer]
      | class Account
      # The billing account of a customer organisation, with the total of its open invoices.
```

A term matches whole words only, so a search for "clients" does not reach it. `origin` says who gave
the meaning: `person` when a person said it, `code` when it was read from the code. When a class
is renamed or moved, its id changes, and `periplus stale` lists the term with the id that is gone.
A meaning a person gave can change with no code change, and nothing marks that:
[How Periplus fits together](architecture.md#what-each-part-knows) says what `periplus stale` can
check.

## What this does not do

Periplus does not work out business meaning that is not in the code. The map tells things apart by
their ids, types, places and links. A person decides what each one means, and the descriptions
keep that decision beside the map.

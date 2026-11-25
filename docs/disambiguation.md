# One word, several things

In many code bases one word names several things. "Account" can be the login of a person and also
the billing record of a customer. This page shows how to tell such things apart with the map, and
how to save the answer so that the next person and the next AI session do not mix them up again.

The work has five steps: find the word, see its meanings, check each in the code, ask a person
where the code cannot say, and save the answer as descriptions. An AI agent with the periplus
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

A short name that fits several things is refused, and Periplus does not pick one.
`periplus show Account` exits with code 31 and lists the 6 ids it fits. A longer name can still be
refused, because other ids end in the same text. Here a parameter type ends in the class name:

```
$ periplus show 'Acme\Billing\Account'
31 'Acme\\\\Billing\\\\Account' matches 2 nodes; give one of these ids
  php.parameter_type::Acme\\Invoice\\StatementBuilder::$account::Acme\\Billing\\Account  php.parameter_type  src/Invoice/StatementBuilder.php:9
  php.type::Acme\\Billing\\Account  php.class  src/Billing/Account.php:5
```

Give the full id, such as `php.type::Acme\Billing\Account`, with single backslashes.

## 2. See its meanings

The map tells the two apart in two ways.

- **By structure.** Each thing has its own id, type, file and line. The ids show two namespaces,
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
periplus find: 2 things (2 main), 0 edges
main by type: php.class 1, php.method 1

php.method::Acme\\Billing\\Account::balance  php.method  mapped  src/Billing/Account.php:7  [description]
      | public function balance(): int
      # Returns the total of the open invoices of a customer organisation.
php.type::Acme\\Billing\\Account  php.class  mapped  src/Billing/Account.php:5  [description]
      | class Account
      # The billing account of a customer organisation, with the total of its open invoices.
```

Do not write what a thing is not. `periplus find` matches every word of a description, so a user
account entry that ended "Not the billing account of a customer organisation" made `periplus find
customer` return both classes.

## What this does not do

Periplus does not work out business meaning that is not in the code. The map tells things apart by
their ids, types, places and links. A person decides what each one means, and the descriptions
keep that decision beside the map.
